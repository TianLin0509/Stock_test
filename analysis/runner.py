"""后台分析任务调度 — 支持多个分析并发执行，不阻塞 UI"""

import logging
import threading
import pandas as pd
from ai.client import call_ai
from ai.context import build_analysis_context
from ai.prompts import (
    build_expectation_prompt,
    build_trend_prompt,
    build_fundamentals_prompt,
    build_sentiment_prompt,
    build_sector_prompt,
    build_holders_prompt,
)
from data.tushare_client import price_summary, to_code6

logger = logging.getLogger(__name__)


def _new_job() -> dict:
    return {"status": "pending", "progress": [], "result": None, "error": None}


def _log(job: dict, msg: str):
    """向 job 追加进度消息"""
    job["progress"].append(msg)


def get_jobs(session_state) -> dict:
    """获取或初始化 jobs 字典"""
    if "_jobs" not in session_state:
        session_state["_jobs"] = {}
    return session_state["_jobs"]


def is_running(session_state, key: str) -> bool:
    jobs = get_jobs(session_state)
    return jobs.get(key, {}).get("status") == "running"


def is_done(session_state, key: str) -> bool:
    jobs = get_jobs(session_state)
    return jobs.get(key, {}).get("status") == "done"


def any_running(session_state) -> bool:
    jobs = get_jobs(session_state)
    return any(j.get("status") == "running" for j in jobs.values())


# ══════════════════════════════════════════════════════════════════════════════
# 数据自取 + prompt 构建（在后台线程中运行，自行获取专属数据）
# ══════════════════════════════════════════════════════════════════════════════

def _build_trend(job, name, tscode, df):
    """趋势分析：线程内并行获取资金/龙虎榜/北向/融资融券数据"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from data.tushare_client import (
        get_capital_flow, get_dragon_tiger,
        get_northbound_flow, get_margin_trading,
    )
    _log(job, "📊 计算K线技术指标 & 并行获取资金数据...")
    psmry = price_summary(df)

    _data_fns = {
        "cap": lambda: get_capital_flow(tscode),
        "dragon": lambda: get_dragon_tiger(tscode),
        "nb": lambda: get_northbound_flow(tscode),
        "margin": lambda: get_margin_trading(tscode),
    }
    _results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fn): key for key, fn in _data_fns.items()}
        for fut in as_completed(futs):
            _results[futs[fut]] = fut.result()

    cap, _ = _results["cap"]
    dragon, _ = _results["dragon"]
    nb, _ = _results["nb"]
    margin, _ = _results["margin"]
    _log(job, "✅ 资金数据获取完成")
    return build_trend_prompt(name, tscode, psmry, cap, dragon, nb, margin)


def _build_sector(job, name, tscode, info):
    """板块分析：线程内获取同行业对比数据"""
    from data.tushare_client import get_sector_peers
    _log(job, "🏭 获取同行业个股对比数据...")
    sector_data, _ = get_sector_peers(tscode)
    return build_sector_prompt(name, tscode, info, sector_data)


def _build_holders(job, name, tscode, info):
    """股东分析：线程内获取股东/质押/基金持仓数据"""
    from data.tushare_client import (
        get_holders_info, get_pledge_info, get_fund_holdings,
    )
    _log(job, "👥 获取十大股东数据...")
    holders, _ = get_holders_info(tscode)
    _log(job, "⚠️ 获取股权质押数据...")
    pledge, _ = get_pledge_info(tscode)
    _log(job, "🏛️ 获取基金持仓数据...")
    fund, _ = get_fund_holdings(tscode)
    return build_holders_prompt(name, tscode, info, holders, pledge, fund)


def start_analysis(session_state, key: str, client, cfg, model_name: str):
    """启动后台分析（如果尚未运行）"""
    jobs = get_jobs(session_state)

    # 已经在跑或已完成，不重复启动
    if key in jobs and jobs[key]["status"] in ("running", "done"):
        return

    job = _new_job()
    jobs[key] = job

    # 从 session_state 读取通用数据（在主线程中读，传给子线程）
    name   = session_state.get("stock_name", "")
    tscode = session_state.get("stock_code", "")
    info   = dict(session_state.get("stock_info", {}))
    fin    = session_state.get("stock_fin", "")
    analyses = dict(session_state.get("analyses", {}))

    # 获取 price_df 的副本（仅趋势分析需要）
    df = session_state.get("price_df", pd.DataFrame())
    if not df.empty:
        df = df.copy()

    # 用户名（用于 token 归属）
    username = session_state.get("current_user", "")

    # 分析调度表：key → (label, build_fn, build_args)
    # 趋势/板块/股东的 build 函数会在线程内自行获取专属数据
    dispatch = {
        "expectation":  ("预期差分析", build_expectation_prompt, (name, tscode, info)),
        "trend":        ("K线趋势研判", _build_trend, (job, name, tscode, df)),
        "fundamentals": ("基本面剖析", build_fundamentals_prompt, (name, tscode, info, fin)),
        "sentiment":    ("舆情情绪分析", build_sentiment_prompt, (name, tscode, info)),
        "sector":       ("板块联动分析", _build_sector, (job, name, tscode, info)),
        "holders":      ("股东/机构动向分析", _build_holders, (job, name, tscode, info)),
    }

    if key in dispatch:
        label, build_fn, build_args = dispatch[key]
        target = _run_generic
        args = (job, client, cfg, model_name, label, build_fn, build_args, username)
    elif key == "moe":
        target = _run_moe
        args = (job, client, cfg, model_name, name, tscode, analyses, username)
    else:
        return

    thread = threading.Thread(target=target, args=args, daemon=True)
    job["status"] = "running"
    thread.start()
    job["_thread"] = thread


def collect_result(session_state, key: str):
    """如果后台任务完成，将结果写入 analyses（主线程调用）"""
    jobs = get_jobs(session_state)
    job = jobs.get(key)
    if not job or job["status"] != "done":
        return

    if key == "moe":
        # MoE 结果直接存在 job 里
        if job.get("moe_data"):
            session_state["moe_results"] = job["moe_data"]
    else:
        analyses = session_state.get("analyses", {})
        if job["result"] and not analyses.get(key):
            analyses[key] = job["result"]
            session_state["analyses"] = analyses


# ══════════════════════════════════════════════════════════════════════════════
# 通用分析模板（在后台线程中执行，不能用 st.* 函数）
# ══════════════════════════════════════════════════════════════════════════════

def _run_generic(job, client, cfg, model_name, label, build_fn, build_args, username=""):
    """通用分析流程：构建 prompt → 流式调用 AI → 逐块累积结果
    job["partial_result"] 实时更新，前端每次 rerun 可展示已生成的内容。
    流式开始前显示心跳消息，流式开始后心跳自动停止。
    """
    import time as _time
    from ai.client import call_ai_stream, add_tokens

    try:
        _log(job, f"📡 正在连接 {model_name}...")
        p, s = build_fn(*build_args)
        _log(job, f"🤖 AI 正在进行{label}...")

        # 心跳：在流式第一个 chunk 到达前显示等待提示
        _first_chunk = threading.Event()
        _tips = [
            "正在联网搜索最新资讯…",
            "正在整理分析数据…",
            "正在等待 AI 响应…",
            "AI 正在思考中…",
            "即将开始输出…",
        ]

        def _heartbeat():
            elapsed = 0
            idx = 0
            while not _first_chunk.wait(timeout=4):
                elapsed += 4
                tip = _tips[min(idx, len(_tips) - 1)]
                _log(job, f"⏱️ 已等待 {elapsed}s — {tip}")
                idx += 1

        hb = threading.Thread(target=_heartbeat, daemon=True)
        hb.start()

        # 流式调用，逐块累积到 partial_result
        job["partial_result"] = ""
        full_text = ""
        has_error = False

        for chunk in call_ai_stream(client, cfg, p, system=s, max_tokens=8000):
            if not _first_chunk.is_set():
                _first_chunk.set()  # 停止心跳
            full_text += chunk
            job["partial_result"] = full_text
            if chunk.startswith("\n\n⚠️"):
                has_error = True

        _first_chunk.set()  # 确保心跳停止

        # 流式完成后估算 token 用量
        if not has_error:
            est_prompt = len(p)
            est_completion = len(full_text)
            add_tokens(
                prompt_tokens=est_prompt,
                completion_tokens=est_completion,
                total_tokens=est_prompt + est_completion,
                username=username,
            )
            _log(job, f"✅ {label}完成！")
            job["result"] = full_text
        else:
            _log(job, f"❌ {label}失败")
            job["result"] = full_text
            job["error"] = full_text

        job["status"] = "done"
    except Exception as e:
        logger.debug("[_run_generic/%s] 异常: %s", label, e)
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ {label}异常：{e}"
        job["status"] = "done"


# ══════════════════════════════════════════════════════════════════════════════
# MoE 辩论（多轮对话，保持独立函数）
# ══════════════════════════════════════════════════════════════════════════════

def _run_moe(job, client, cfg, model_name, name, tscode, analyses, username=""):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from analysis.moe import MOE_ROLES, CEO_SYSTEM
    code6 = to_code6(tscode)

    try:
        _log(job, "📋 汇总预期差、趋势、基本面三项分析结果...")
        context = build_analysis_context(analyses, max_per_module=15)
        _log(job, "🏟️ 召集五方专家并行发表观点...")

        def _call_role(role):
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
                                system=role["system"], max_tokens=800,
                                username=username)
            if err:
                text = f"⚠️ 该角色分析失败：{err}"
            return role, text

        role_results = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = {pool.submit(_call_role, role): role for role in MOE_ROLES}
            done_count = 0
            for fut in as_completed(futs):
                role, text = fut.result()
                role_results[role["key"]] = text
                done_count += 1
                _log(job, f"  ✓ [{done_count}/{len(MOE_ROLES)}] {role['badge']} 观点已提交")

        _log(job, "👔 首席执行官正在综合五方观点，做最终裁决...")

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
                                     system=CEO_SYSTEM, max_tokens=2000,
                                     username=username)
        if ceo_err:
            ceo_text = f"⚠️ CEO裁决生成失败：{ceo_err}\n\n建议切换其他模型后重新尝试。"

        _log(job, "✅ MoE 五方辩论裁决完成！")
        job["moe_data"] = {"roles": role_results, "ceo": ceo_text, "done": True}
        job["result"] = "done"
        job["status"] = "done"

    except Exception as e:
        logger.debug("[_run_moe] 异常: %s", e)
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ MoE 辩论异常：{e}"
        job["status"] = "done"
