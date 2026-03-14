"""后台分析调度 — 数据增强 + 并行评分"""

import json
import os
import threading
from datetime import date
import pandas as pd
import streamlit as st
from ai.client import get_ai_client, call_ai
from top10.prompts import SYSTEM_SUMMARY, build_summary_prompt
from top10.scorer import score_all


# ══════════════════════════════════════════════════════════════════════════════
# 持久化缓存（session_state + JSON 文件双重保险）
# ══════════════════════════════════════════════════════════════════════════════

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_key(model_name: str) -> str:
    return f"top10_result_{date.today().isoformat()}_{model_name}"


def _summary_key(model_name: str) -> str:
    return f"top10_summary_{date.today().isoformat()}_{model_name}"


def _file_path(model_name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{date.today().isoformat()}_{model_name}.json")


def get_cached_result(model_name: str) -> pd.DataFrame | None:
    """优先读 session_state，否则读文件"""
    key = _cache_key(model_name)
    if key in st.session_state:
        return st.session_state[key]
    # 尝试读文件
    fp = _file_path(model_name)
    if os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            df = pd.DataFrame(data["results"])
            df.index = df.index + 1
            df.index.name = "推荐排名"
            st.session_state[key] = df
            skey = _summary_key(model_name)
            if "summary" in data:
                st.session_state[skey] = data["summary"]
            return df
        except Exception:
            pass
    return None


def get_cached_summary(model_name: str) -> str | None:
    skey = _summary_key(model_name)
    if skey in st.session_state:
        return st.session_state[skey]
    # 触发文件读取（会同时加载 summary）
    get_cached_result(model_name)
    return st.session_state.get(skey)


def save_cached_result(model_name: str, df: pd.DataFrame, summary: str = ""):
    st.session_state[_cache_key(model_name)] = df
    if summary:
        st.session_state[_summary_key(model_name)] = summary
    # 写入文件持久化
    try:
        # 只保存可序列化的列
        save_cols = [c for c in df.columns if c != "K线摘要"]
        data = {
            "results": df[save_cols].to_dict(orient="records"),
            "summary": summary,
            "model": model_name,
            "date": date.today().isoformat(),
        }
        with open(_file_path(model_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def get_all_cached_models() -> list[str]:
    """获取今日所有已缓存的模型名称"""
    today_str = date.today().isoformat()
    models = []
    for fn in os.listdir(_CACHE_DIR):
        if fn.startswith(today_str) and fn.endswith(".json"):
            model = fn[len(today_str) + 1:-5]  # 去掉日期前缀和.json
            models.append(model)
    return models


# ══════════════════════════════════════════════════════════════════════════════
# 后台任务管理
# ══════════════════════════════════════════════════════════════════════════════

def get_job(ss) -> dict:
    return ss.get("top10_bg_job", {})


def is_running(ss) -> bool:
    return get_job(ss).get("status") == "running"


def is_done(ss) -> bool:
    return get_job(ss).get("status") == "done"


def start_scoring(ss, candidates_df: pd.DataFrame, model_name: str):
    """启动后台评分线程"""
    if is_running(ss):
        return

    client, cfg, err = get_ai_client(model_name)
    if err:
        ss["top10_bg_job"] = {"status": "done", "error": err, "progress": [f"❌ {err}"]}
        return

    job = {
        "status": "running",
        "progress": [],
        "error": None,
        "result": None,
        "summary": None,
        "model": model_name,
        "total": len(candidates_df),
        "current": 0,
    }
    ss["top10_bg_job"] = job

    def _run():
        try:
            # Phase 1: 数据增强
            job["progress"].append("📊 正在从 Tushare 获取增强数据（PE/PB/K线）...")
            try:
                from top10.tushare_data import enrich_candidates, ts_ok
                if ts_ok():
                    enriched_df = enrich_candidates(
                        candidates_df,
                        progress_callback=lambda msg: job["progress"].append(f"  {msg}")
                    )
                    job["progress"].append(f"✅ 数据增强完成（行业/PE/PB/K线摘要）")
                else:
                    enriched_df = candidates_df
                    job["progress"].append("⚠️ Tushare 不可用，使用基础数据分析")
            except Exception as e:
                enriched_df = candidates_df
                job["progress"].append(f"⚠️ 数据增强失败({e})，使用基础数据")

            # Phase 2: 并行 AI 评分
            total = len(enriched_df)
            job["progress"].append(f"🤖 开始并行AI评分，共 {total} 只候选股（3路并发）...")

            def progress_cb(current, total, msg):
                job["current"] = current
                job["progress"].append(f"[{current}/{total}] {msg}")

            scored = score_all(client, cfg, enriched_df,
                               model_name=model_name,
                               progress_callback=progress_cb,
                               max_workers=3)

            job["progress"].append(f"✅ 评分完成！共评分 {len(scored)} 只股票")
            job["result"] = scored

            # Phase 3: 生成总结报告
            job["progress"].append("📝 正在生成每日总结报告...")
            summary = ""
            try:
                top10 = scored.head(10)
                stock_lines = []
                for _, r in top10.iterrows():
                    line = (f"- {r['股票名称']}({r['代码']}) "
                            f"行业:{r.get('行业','未知')} "
                            f"综合评分{r['综合评分']}/10 "
                            f"短线建议:{r.get('短线建议','未知')}")
                    stock_lines.append(line)
                stocks_text = "\n".join(stock_lines)

                # 加入板块轮动信号
                try:
                    from top10.tushare_data import get_sector_rotation
                    sectors = get_sector_rotation()
                    if sectors.get("概念板块"):
                        stocks_text += "\n\n今日概念板块涨幅Top5：" + "、".join(sectors["概念板块"])
                    if sectors.get("行业板块"):
                        stocks_text += "\n今日行业板块涨幅Top5：" + "、".join(sectors["行业板块"])
                except Exception:
                    pass

                summary_prompt = build_summary_prompt(stocks_text, total)
                summary, s_err = call_ai(
                    client, cfg, summary_prompt,
                    system=SYSTEM_SUMMARY, max_tokens=4000
                )
                if s_err:
                    summary = f"总结生成失败：{s_err}"
            except Exception as se:
                summary = f"总结生成失败：{se}"

            job["summary"] = summary
            job["progress"].append("✅ 全部完成！")
            job["status"] = "done"

            save_cached_result(model_name, scored, summary)

        except Exception as e:
            job["error"] = str(e)
            job["progress"].append(f"❌ 分析出错：{e}")
            job["status"] = "done"

    t = threading.Thread(target=_run, daemon=True)
    t.start()
