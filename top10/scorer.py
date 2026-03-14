"""逐只评分 + 排名（支持并行）"""

import re
import math
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from ai.client import call_ai
from top10.prompts import SYSTEM_SCORER, build_score_prompt


def _parse_score(text: str) -> float:
    """从 AI 回复中提取综合评分"""
    m = re.search(r"综合评分[：:]\s*[*]*(\d+\.?\d*)\s*/\s*10", text)
    if m:
        return float(m.group(1))
    m = re.search(r"\*\*\s*(\d+\.?\d*)\s*/\s*10\s*\*\*", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+\.?\d*)\s*/\s*10", text)
    if m:
        return float(m.group(1))
    return 0.0


def _parse_sub_scores(text: str) -> dict:
    """从 AI 回复中提取三项子评分"""
    scores = {}
    for label in ["基本面", "题材热度", "技术面"]:
        m = re.search(rf"{label}\s*\|\s*(\d+\.?\d*)\s*/\s*10", text)
        if m:
            scores[label] = float(m.group(1))
    return scores


def _parse_advice(text: str) -> str:
    """从 AI 回复中提取短线建议"""
    m = re.search(r"短线建议[：:]\s*[*]*\s*(强烈推荐|推荐|观望|回避)", text)
    if m:
        return m.group(1)
    return ""


def _safe_float(v):
    if v is None:
        return None
    try:
        val = float(v)
        return None if math.isnan(val) else val
    except (ValueError, TypeError):
        return None


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def score_single_stock(client, cfg, row: pd.Series,
                       model_name: str = "") -> dict:
    """对单只股票进行 AI 评分，返回结果字典"""
    code = str(row.get("代码", ""))
    name = str(row.get("股票名称", ""))
    price = _safe_float(row.get("最新价", 0)) or 0.0
    change = _safe_float(row.get("涨跌幅", 0)) or 0.0
    hot_rank = _safe_int(row.get("人气排名") if "人气排名" in row.index else None)
    vol_rank = _safe_int(row.get("成交额排名") if "成交额排名" in row.index else None)
    volume_yi = _safe_float(row.get("成交额(亿)") if "成交额(亿)" in row.index else None)
    turnover_rate = _safe_float(row.get("换手率") if "换手率" in row.index else None)
    volume_ratio = _safe_float(row.get("量比") if "量比" in row.index else None)
    net_flow_wan = _safe_float(row.get("主力净流入(万)") if "主力净流入(万)" in row.index else None)
    pe = _safe_float(row.get("PE") if "PE" in row.index else None)
    pb = _safe_float(row.get("PB") if "PB" in row.index else None)
    mkt_cap_yi = _safe_float(row.get("总市值(亿)") if "总市值(亿)" in row.index else None)
    industry = row.get("行业", "") if "行业" in row.index else None
    kline_summary = row.get("K线摘要", "") if "K线摘要" in row.index else None

    # 新增：行业基准
    industry_pe = _safe_float(row.get("行业PE均值") if "行业PE均值" in row.index else None)
    industry_pb = _safe_float(row.get("行业PB均值") if "行业PB均值" in row.index else None)

    # 新增：量化预评分
    quant_score = None
    if "量化总分" in row.index and row.get("量化总分") is not None:
        quant_score = {
            "技术面分": _safe_int(row.get("技术面分")),
            "资金面分": _safe_int(row.get("资金面分")),
            "估值面分": _safe_int(row.get("估值面分")),
            "动量分": _safe_int(row.get("动量分")),
            "量化总分": _safe_int(row.get("量化总分")),
            "量化信号": row.get("量化信号", ""),
        }

    prompt = build_score_prompt(
        code, name, price, change,
        hot_rank, vol_rank, volume_yi,
        turnover_rate, volume_ratio, net_flow_wan,
        pe, pb, mkt_cap_yi, industry, kline_summary,
        industry_pe, industry_pb, quant_score
    )
    text, err = call_ai(client, cfg, prompt,
                        system=SYSTEM_SCORER, max_tokens=4000)

    score = _parse_score(text) if not err else 0.0
    sub_scores = _parse_sub_scores(text) if not err else {}
    advice = _parse_advice(text) if not err else ""

    return {
        "代码": code,
        "股票名称": name,
        "最新价": price,
        "涨跌幅": change,
        "行业": industry or "",
        "综合评分": score,
        "基本面": sub_scores.get("基本面"),
        "题材热度": sub_scores.get("题材热度"),
        "技术面": sub_scores.get("技术面"),
        "短线建议": advice,
        "AI分析": text if not err else f"分析失败：{err}",
        "模型": model_name,
        "人气排名": hot_rank,
        "成交额排名": vol_rank,
        "量化总分": _safe_int(row.get("量化总分")) if "量化总分" in row.index else None,
        "量化信号": row.get("量化信号", "") if "量化信号" in row.index else "",
    }


def score_all(client, cfg, df: pd.DataFrame,
              model_name: str = "",
              progress_callback=None,
              max_workers: int = 3) -> pd.DataFrame:
    """对整个候选池并行评分，返回按评分排序的 DataFrame"""
    results = []
    total = len(df)
    completed_count = 0

    def _score_row(idx_row):
        _, row = idx_row
        return score_single_stock(client, cfg, row, model_name)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_score_row, (idx, row)): row["股票名称"]
            for idx, row in df.iterrows()
        }
        for future in as_completed(futures):
            name = futures[future]
            completed_count += 1
            try:
                result = future.result()
                results.append(result)
                qs = result.get("量化总分", "")
                qs_str = f"(量化{qs})" if qs else ""
                if progress_callback:
                    progress_callback(completed_count, total,
                                      f"✅ {name} → {result['综合评分']}/10 {qs_str}")
            except Exception as e:
                if progress_callback:
                    progress_callback(completed_count, total,
                                      f"❌ {name} 分析失败：{e}")

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("综合评分", ascending=False).reset_index(drop=True)
    result_df.index = result_df.index + 1
    result_df.index.name = "推荐排名"
    return result_df


def get_top_n(scored_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """取评分最高的 N 只"""
    if scored_df.empty:
        return scored_df
    return scored_df.head(n)
