"""深度 Top10 流水线 — 100 只候选全量深度分析 + 排序筛选

流程：
Phase 1: 获取候选池（人气榜+成交额榜 → 合并 → 初筛 → 100只）
Phase 2: Tushare 数据增强（PE/PB/K线摘要/行业）
Phase 3: 并行 AI 三维评分（基本面/题材/技术面）
Phase 4: 对所有已评分股票做深度分析（6维 + MoE）写入 shared_cache
Phase 5: 排序取 Top10，生成一句话精选理由
Phase 6: 保存缓存 + 发送邮件
"""

import json
import logging
import os
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger(__name__)

# 状态文件（跨 session 可见）
_STATUS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
os.makedirs(_STATUS_DIR, exist_ok=True)

_running_lock = threading.Lock()
_is_running = False


def _status_file() -> str:
    return os.path.join(_STATUS_DIR, f"{date.today().isoformat()}_deep_status.json")


def _write_status(status: dict):
    try:
        with open(_status_file(), "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def get_deep_status() -> dict | None:
    """获取今日深度分析状态"""
    fp = _status_file()
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_deep_running() -> bool:
    global _is_running
    with _running_lock:
        return _is_running


def _fetch_stock_data(code6: str):
    """获取单只股票的基础数据（info/K线/财务），用于深度分析"""
    from data.tushare_client import (
        get_basic_info, get_price_df, get_financial, to_ts_code,
    )
    ts_code = to_ts_code(code6)
    info, _ = get_basic_info(ts_code)
    price_df, _ = get_price_df(ts_code)
    fin, _ = get_financial(ts_code)
    return ts_code, info, price_df, fin


def _deep_analyze_one(client, cfg, model_name: str,
                      code6: str, name: str, username: str = "") -> dict | None:
    """对单只股票做完整深度分析（6维 + MoE），返回 shared_cache 格式的数据"""
    from ai.client import call_ai
    from ai.prompts import (
        build_expectation_prompt, build_trend_prompt,
        build_fundamentals_prompt, build_sentiment_prompt,
        build_sector_prompt, build_holders_prompt,
    )
    from ai.context import build_analysis_context
    from data.tushare_client import (
        price_summary, to_ts_code, to_code6,
        get_capital_flow, get_dragon_tiger,
        get_northbound_flow, get_margin_trading,
        get_sector_peers, get_holders_info, get_pledge_info, get_fund_holdings,
    )

    try:
        ts_code = to_ts_code(code6)
        info, price_df, fin = {}, pd.DataFrame(), ""

        # 获取基础数据
        from data.tushare_client import get_basic_info, get_price_df, get_financial
        info, _ = get_basic_info(ts_code)
        price_df, _ = get_price_df(ts_code)
        fin, _ = get_financial(ts_code)

        analyses = {}

        # 1. 预期差
        p, s = build_expectation_prompt(name, ts_code, info)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["expectation"] = text

        # 2. K线趋势
        psmry = price_summary(price_df) if not price_df.empty else ""
        cap, _ = get_capital_flow(ts_code)
        dragon, _ = get_dragon_tiger(ts_code)
        nb, _ = get_northbound_flow(ts_code)
        margin, _ = get_margin_trading(ts_code)
        p, s = build_trend_prompt(name, ts_code, psmry, cap, dragon, nb, margin)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["trend"] = text

        # 3. 基本面
        p, s = build_fundamentals_prompt(name, ts_code, info, fin)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["fundamentals"] = text

        # 4. 舆情
        p, s = build_sentiment_prompt(name, ts_code, info)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["sentiment"] = text

        # 5. 板块联动
        sector_data, _ = get_sector_peers(ts_code)
        p, s = build_sector_prompt(name, ts_code, info, sector_data)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["sector"] = text

        # 6. 股东/机构
        holders, _ = get_holders_info(ts_code)
        pledge, _ = get_pledge_info(ts_code)
        fund, _ = get_fund_holdings(ts_code)
        p, s = build_holders_prompt(name, ts_code, info, holders, pledge, fund)
        text, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if not err:
            analyses["holders"] = text

        # 7. MoE 辩论（需要核心三项完成）
        moe_results = None
        core_ok = all(analyses.get(k) for k in ["expectation", "trend", "fundamentals"])
        if core_ok:
            moe_results = _run_moe_standalone(
                client, cfg, model_name, name, code6, analyses, username
            )

        # 保存到 shared_cache
        from utils.shared_cache import save_shared
        save_shared(
            stock_code=ts_code, stock_name=name, model_name=model_name,
            username=username, analyses=analyses, moe_results=moe_results,
            stock_info=info,
        )

        return {
            "analyses": analyses,
            "moe_results": moe_results,
            "stock_info": info,
        }

    except Exception as e:
        logger.warning("[deep_analyze] %s(%s) 失败: %s", name, code6, e)
        return None


def _run_moe_standalone(client, cfg, model_name, name, code6, analyses, username=""):
    """独立 MoE 辩论（不依赖 session_state）"""
    from ai.client import call_ai
    from ai.context import build_analysis_context
    from analysis.moe import MOE_ROLES, CEO_SYSTEM

    context = build_analysis_context(analyses, max_per_module=15)
    role_results = {}

    for role in MOE_ROLES:
        prompt = f"""辩论标的：{name}（{code6}）

## 分析背景
{context}

---
从你的角色视角给出明确判断，控制在250字以内：

**核心判断：** 看多/看空/中性/观望
**判断依据（3条，引用上方分析中的具体数据）：**
1.
2.
3.
**操作建议：**（具体操作+入场价+止损价+目标价）
**最大风险：**（1条，具体描述）

保持角色特色和语言风格。"""
        text, err = call_ai(client, cfg, prompt,
                            system=role["system"], max_tokens=800, username=username)
        if err:
            text = f"⚠️ 分析失败：{err}"
        role_results[role["key"]] = text

    # CEO 裁决
    roles_text = "\n\n".join(
        f"【{r['badge']}】\n{role_results.get(r['key'], '')}"
        for r in MOE_ROLES
    )
    ceo_prompt = f"""标的：{name}（{code6}）

## 五位专家观点
{roles_text}

## 原始分析摘要
{context}

---
综合以上信息给出最终操作裁决。
⚠️ **散户（韭菜代表）的观点是反向指标，逆向参考。**
💡 **特别关注价值投机手的「三维共振」判断，若基本面+题材+技术三者不共振，需降级评价。**

## 🎯 最终操作结论

**操作评级：** 强烈买入/买入/谨慎介入/持有观察/减持/回避

**裁决逻辑（3-4句，说明为什么这样判断）：**

**目标价体系：**
| 维度 | 价格 | 依据 |
|-----|-----|-----|
| 当前股价 | ___元 | — |
| 短线目标（1-2周）| | |
| 中线目标（1-3月）| | |
| 止损位 | | |

**仓位策略：** 建议仓位___%, 介入方式：___

**核心逻辑（2条）：**
1.
2.

**核心风险（2条）：**
1.
2.

**策略有效期：** ___个交易日，若___则策略失效。"""

    ceo_text, ceo_err = call_ai(client, cfg, ceo_prompt,
                                 system=CEO_SYSTEM, max_tokens=2000, username=username)
    if ceo_err:
        ceo_text = f"⚠️ CEO裁决失败：{ceo_err}"

    return {"roles": role_results, "ceo": ceo_text, "done": True}


def _generate_one_liner(client, cfg, name: str, code6: str,
                        score: float, analyses: dict, username: str = "") -> str:
    """为 Top 股票生成一句话精选理由"""
    from ai.client import call_ai

    # 取核心分析摘要（截断以节省 token）
    snippets = []
    for k in ["expectation", "trend", "fundamentals"]:
        text = analyses.get(k, "")
        if text:
            snippets.append(text[:500])
    context = "\n---\n".join(snippets)

    prompt = f"""你是顶级投资顾问。根据以下分析摘要，为 {name}({code6}) 写一句话推荐理由（不超过40字）。
综合评分：{score}/10

分析摘要：
{context}

要求：
- 突出最核心的投资逻辑（不要泛泛而谈）
- 包含具体数据或事实（如：PE仅15倍、订单同比增长50%、突破年线放量）
- 明确给出短线建议方向
- 不超过40字"""

    text, err = call_ai(client, cfg, prompt, max_tokens=200, username=username)
    if err:
        return ""
    return text.strip().strip('"').strip("'")


def run_deep_top10(model_name: str = "🟤 豆包 · Seed 2.0 Mini",
                   candidate_count: int = 100,
                   username: str = "auto_scheduler",
                   progress_callback=None):
    """执行完整深度 Top10 分析流水线"""
    global _is_running
    from ai.client import get_ai_client, get_token_usage
    from top10.hot_rank import get_hot_rank, get_volume_rank, merge_candidates
    from top10.stock_filter import apply_filters
    from top10.tushare_data import enrich_candidates, ts_ok
    from top10.scorer import score_all
    from top10.runner import save_cached_result

    with _running_lock:
        if _is_running:
            logger.warning("[deep_top10] 已有任务在运行，跳过")
            return
        _is_running = True

    def _log(msg):
        logger.info("[deep_top10] %s", msg)
        if progress_callback:
            progress_callback(msg)

    status = {
        "status": "running", "started": datetime.now().isoformat(),
        "model": model_name, "username": username,
        "phase": "", "progress": [], "error": None,
    }
    _write_status(status)

    tokens_before = get_token_usage()["total"]

    try:
        # ── Phase 1: 获取候选池 ──────────────────────────────────
        status["phase"] = "获取候选池"
        _write_status(status)
        _log("📡 Phase 1: 获取候选池...")

        hot_df, _ = get_hot_rank(candidate_count)
        vol_df, _ = get_volume_rank(candidate_count)
        merged = merge_candidates(hot_df, vol_df)
        filtered = apply_filters(merged)
        candidates = filtered.head(candidate_count)
        _log(f"  候选池: 人气榜{len(hot_df)} + 成交额榜{len(vol_df)} → 合并去重过滤 → {len(candidates)} 只")

        if candidates.empty:
            raise RuntimeError("候选池为空")

        # ── Phase 2: 数据增强 ────────────────────────────────────
        status["phase"] = "数据增强"
        _write_status(status)
        _log("📊 Phase 2: Tushare 数据增强...")

        if ts_ok():
            enriched = enrich_candidates(
                candidates,
                progress_callback=lambda msg: _log(f"  {msg}")
            )
            _log("  ✅ 数据增强完成")
        else:
            enriched = candidates
            _log("  ⚠️ Tushare 不可用，使用基础数据")

        # ── Phase 3: AI 三维评分 ─────────────────────────────────
        status["phase"] = "AI评分"
        _write_status(status)
        _log(f"🤖 Phase 3: AI 三维评分（{len(enriched)} 只，3路并发）...")

        client, cfg, err = get_ai_client(model_name)
        if err:
            raise RuntimeError(f"AI 客户端初始化失败: {err}")

        def score_progress(current, total, msg):
            _log(f"  [{current}/{total}] {msg}")
            status["progress"].append(f"[评分] {current}/{total}")
            _write_status(status)

        scored = score_all(client, cfg, enriched,
                           model_name=model_name,
                           progress_callback=score_progress,
                           max_workers=3)

        _log(f"  ✅ 评分完成，共 {len(scored)} 只")

        # ── Phase 4: 全量深度分析 ────────────────────────────────
        status["phase"] = "深度分析"
        _write_status(status)
        total = len(scored)
        _log(f"🔬 Phase 4: 全量深度分析（{total} 只，2路并发）...")

        deep_results = {}  # code6 → {analyses, moe_results, ...}
        completed = 0

        def _analyze_one(row):
            code6 = str(row.get("代码", ""))
            name = str(row.get("股票名称", ""))
            return code6, _deep_analyze_one(client, cfg, model_name, code6, name, username)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(_analyze_one, row): row["股票名称"]
                for _, row in scored.iterrows()
            }
            for future in as_completed(futures):
                name = futures[future]
                completed += 1
                try:
                    code6, result = future.result()
                    if result:
                        deep_results[code6] = result
                        _log(f"  [{completed}/{total}] ✅ {name} 深度分析完成")
                    else:
                        _log(f"  [{completed}/{total}] ⚠️ {name} 深度分析部分失败")
                except Exception as e:
                    _log(f"  [{completed}/{total}] ❌ {name} 深度分析异常: {e}")
                status["progress"].append(f"[深度] {completed}/{total}")
                _write_status(status)

        # ── Phase 5: Top10 一句话理由 ────────────────────────────
        status["phase"] = "生成精选理由"
        _write_status(status)
        _log("📝 Phase 5: 为 Top10 生成一句话精选理由...")

        top10 = scored.head(10)
        one_liners = {}
        for _, row in top10.iterrows():
            code6 = str(row["代码"])
            name = str(row["股票名称"])
            score = row["综合评分"]
            deep = deep_results.get(code6, {})
            analyses_data = deep.get("analyses", {})
            liner = _generate_one_liner(client, cfg, name, code6, score, analyses_data, username)
            one_liners[code6] = liner
            if liner:
                _log(f"  {name}: {liner}")

        # 将一句话理由写入 scored DataFrame
        scored["一句话理由"] = scored["代码"].map(one_liners).fillna("")

        # ── Phase 6: 生成总结 + 保存 + 邮件 ──────────────────────
        status["phase"] = "总结保存"
        _write_status(status)
        _log("📋 Phase 6: 生成总结报告...")

        # 生成总结
        from top10.prompts import SYSTEM_SUMMARY, build_summary_prompt
        stock_lines = []
        for _, r in top10.iterrows():
            line = (f"- {r['股票名称']}({r['代码']}) "
                    f"行业:{r.get('行业', '未知')} "
                    f"综合评分{r['综合评分']}/10 "
                    f"短线建议:{r.get('短线建议', '未知')} "
                    f"中期建议:{r.get('中期建议', '未知')}")
            liner = one_liners.get(str(r["代码"]), "")
            if liner:
                line += f" 推荐理由:{liner}"
            stock_lines.append(line)
        stocks_text = "\n".join(stock_lines)

        try:
            from top10.tushare_data import get_sector_rotation
            sectors = get_sector_rotation()
            if sectors.get("概念板块"):
                stocks_text += "\n\n今日概念板块涨幅Top5：" + "、".join(sectors["概念板块"])
            if sectors.get("行业板块"):
                stocks_text += "\n今日行业板块涨幅Top5：" + "、".join(sectors["行业板块"])
        except Exception:
            pass

        from ai.client import call_ai
        summary_prompt = build_summary_prompt(stocks_text, len(candidates))
        summary, s_err = call_ai(client, cfg, summary_prompt,
                                  system=SYSTEM_SUMMARY, max_tokens=4000, username=username)
        if s_err:
            summary = f"总结生成失败：{s_err}"

        # 计算 token 消耗
        tokens_after = get_token_usage()["total"]
        tokens_used = tokens_after - tokens_before

        # 保存到 Top10 缓存
        save_cached_result(model_name, scored, summary,
                           triggered_by=username, tokens_used=tokens_used)

        _log(f"✅ 全部完成！共消耗 {tokens_used:,} token")

        # 发送邮件
        _log("📧 发送 Top10 报告邮件...")
        from top10.runner import _send_top10_email
        _send_top10_email(summary, scored, model_name, username, tokens_used)

        # 更新状态
        status["status"] = "done"
        status["phase"] = "完成"
        status["finished"] = datetime.now().isoformat()
        status["tokens_used"] = tokens_used
        status["scored_count"] = len(scored)
        status["deep_count"] = len(deep_results)
        _write_status(status)

    except Exception as e:
        logger.error("[deep_top10] 异常: %s", e, exc_info=True)
        status["status"] = "error"
        status["error"] = str(e)
        _write_status(status)
    finally:
        with _running_lock:
            _is_running = False


def start_deep_top10_async(model_name: str = "🟤 豆包 · Seed 2.0 Mini",
                           candidate_count: int = 100,
                           username: str = "auto_scheduler"):
    """在后台线程中启动深度 Top10 分析"""
    if is_deep_running():
        return False
    t = threading.Thread(
        target=run_deep_top10,
        kwargs={"model_name": model_name, "candidate_count": candidate_count,
                "username": username},
        daemon=True,
    )
    t.start()
    return True
