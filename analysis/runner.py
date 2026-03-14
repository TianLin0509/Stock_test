"""后台分析任务调度 — 支持多个分析并发执行，不阻塞 UI"""

import time
import threading
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


def start_analysis(session_state, key: str, client, cfg, model_name: str):
    """启动后台分析（如果尚未运行）"""
    jobs = get_jobs(session_state)

    # 已经在跑或已完成，不重复启动
    if key in jobs and jobs[key]["status"] in ("running", "done"):
        return

    job = _new_job()
    jobs[key] = job

    # 从 session_state 读取所有需要的数据（在主线程中读，传给子线程）
    name   = session_state.get("stock_name", "")
    tscode = session_state.get("stock_code", "")
    info   = dict(session_state.get("stock_info", {}))
    fin    = session_state.get("stock_fin", "")
    cap    = session_state.get("stock_cap", "")
    dragon = session_state.get("stock_dragon", "")
    northbound = session_state.get("stock_northbound", "")
    margin = session_state.get("stock_margin", "")
    analyses = dict(session_state.get("analyses", {}))

    # 获取 price_df 的副本
    import pandas as pd
    df = session_state.get("price_df", pd.DataFrame())
    if not df.empty:
        df = df.copy()

    # 额外数据（板块/股东）
    holders  = session_state.get("stock_holders", "")
    pledge   = session_state.get("stock_pledge", "")
    fund_hold = session_state.get("stock_fund_holdings", "")
    sector   = session_state.get("stock_sector_peers", "")

    # 用户名（用于 token 归属）
    username = session_state.get("current_user", "")

    # 选择对应的分析函数
    if key == "expectation":
        target = _run_expectation
        args = (job, client, cfg, model_name, name, tscode, info, username)
    elif key == "trend":
        target = _run_trend
        args = (job, client, cfg, model_name, name, tscode, df, cap, dragon, northbound, margin, username)
    elif key == "fundamentals":
        target = _run_fundamentals
        args = (job, client, cfg, model_name, name, tscode, info, fin, username)
    elif key == "sentiment":
        target = _run_sentiment
        args = (job, client, cfg, model_name, name, tscode, info, username)
    elif key == "sector":
        target = _run_sector
        args = (job, client, cfg, model_name, name, tscode, info, sector, username)
    elif key == "holders":
        target = _run_holders
        args = (job, client, cfg, model_name, name, tscode, info, holders, pledge, fund_hold, username)
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
# 各分析任务（在后台线程中执行，不能用 st.* 函数）
# ══════════════════════════════════════════════════════════════════════════════

def _run_expectation(job, client, cfg, model_name, name, tscode, info, username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        _log(job, f"🌐 联网搜索 {name} 最新资讯、研报、公告...")
        time.sleep(0.5)
        _log(job, "📰 整理市场预期与实际情况的差异...")
        p, s = build_expectation_prompt(name, tscode, info)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在深度分析预期差，通常需要 15~30 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 预期差分析失败：{err}")
            job["result"] = f"⚠️ 预期差分析失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 正在整理分析结论...")
        time.sleep(0.3)
        _log(job, "✅ 预期差分析完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 预期差分析异常：{e}"
        job["status"] = "done"


def _run_trend(job, client, cfg, model_name, name, tscode, df, cap, dragon,
               northbound="", margin="", username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        _log(job, "📊 读取近 140 日K线数据...")
        time.sleep(0.4)
        _log(job, "📐 计算均线系统（MA5 / MA20 / MA60）...")
        psmry = price_summary(df)
        time.sleep(0.4)
        _log(job, "💰 分析主力资金流向...")
        time.sleep(0.3)
        _log(job, "🐉 检索龙虎榜数据...")
        time.sleep(0.3)
        if northbound and northbound != "暂无北向资金持仓数据":
            _log(job, "🌏 分析北向资金持仓变化...")
            time.sleep(0.3)
        if margin and margin != "暂无融资融券数据":
            _log(job, "📊 分析融资融券趋势...")
            time.sleep(0.3)
        _log(job, "📐 构建技术分析框架（支撑位 / 压力位 / 形态识别）...")
        p, s = build_trend_prompt(name, tscode, psmry, cap, dragon,
                                  northbound, margin)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在研判趋势走向，通常需要 15~30 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 趋势研判失败：{err}")
            job["result"] = f"⚠️ 趋势研判失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 正在整理研判结论...")
        time.sleep(0.3)
        _log(job, "✅ K线趋势研判完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 趋势研判异常：{e}"
        job["status"] = "done"


def _run_fundamentals(job, client, cfg, model_name, name, tscode, info, fin, username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        _log(job, "📑 读取财务报表（利润表 / 资产负债表 / 现金流）...")
        time.sleep(0.5)
        _log(job, "🔢 计算核心指标（ROE / 毛利率 / 营收增速 / 负债率）...")
        time.sleep(0.4)
        _log(job, "🏭 对比行业估值水平与竞争格局...")
        p, s = build_fundamentals_prompt(name, tscode, info, fin)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在深度剖析基本面，通常需要 15~30 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 基本面剖析失败：{err}")
            job["result"] = f"⚠️ 基本面剖析失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 正在整理分析结论...")
        time.sleep(0.3)
        _log(job, "✅ 基本面剖析完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 基本面剖析异常：{e}"
        job["status"] = "done"


def _run_moe(job, client, cfg, model_name, name, tscode, analyses, username=""):
    from analysis.moe import MOE_ROLES, CEO_SYSTEM
    code6 = to_code6(tscode)

    try:
        _log(job, "📋 汇总预期差、趋势、基本面三项分析结果...")
        time.sleep(0.5)
        context = build_analysis_context(analyses, max_per_module=15)
        _log(job, "🏟️ 召集五方专家进入辩论会场...")
        time.sleep(0.5)

        role_results = {}
        for i, role in enumerate(MOE_ROLES, 1):
            _log(job, f"🎙️ [{i}/{len(MOE_ROLES)}] {role['badge']} 正在发表观点...")
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
            role_results[role["key"]] = text
            _log(job, f"  ✓ {role['badge']} 观点已提交")
            time.sleep(0.3)

        _log(job, "👔 首席执行官正在综合五方观点，做最终裁决...")
        time.sleep(0.4)

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
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ MoE 辩论异常：{e}"
        job["status"] = "done"


def _run_sentiment(job, client, cfg, model_name, name, tscode, info, username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        _log(job, f"🔍 搜索雪球（xueqiu.com）关于 {name} 的讨论...")
        time.sleep(0.5)
        _log(job, "🔍 搜索东方财富股吧热帖...")
        time.sleep(0.4)
        _log(job, "🔍 搜索同花顺、财联社等财经媒体...")
        time.sleep(0.4)
        _log(job, "🧹 过滤灌水/广告/无效内容，提取高质量讨论...")
        p, s = build_sentiment_prompt(name, tscode, info)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在分析舆情情绪，通常需要 20~40 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 舆情分析失败：{err}")
            job["result"] = f"⚠️ 舆情分析失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 整理舆情分析结论...")
        time.sleep(0.3)
        _log(job, "✅ 舆情情绪分析完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 舆情分析异常：{e}"
        job["status"] = "done"


def _run_sector(job, client, cfg, model_name, name, tscode, info, sector_data, username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        industry = info.get("行业", "未知")
        _log(job, f"🏭 分析 {industry} 板块整体态势...")
        time.sleep(0.5)
        _log(job, f"🔍 联网搜索 {industry} 板块近期资金流向与催化事件...")
        time.sleep(0.4)
        _log(job, f"📊 对比 {name} 与同行业个股估值/走势...")
        p, s = build_sector_prompt(name, tscode, info, sector_data)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在进行板块联动分析，通常需要 15~30 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 板块分析失败：{err}")
            job["result"] = f"⚠️ 板块分析失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 整理板块分析结论...")
        time.sleep(0.3)
        _log(job, "✅ 板块联动分析完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 板块分析异常：{e}"
        job["status"] = "done"


def _run_holders(job, client, cfg, model_name, name, tscode, info,
                 holders_data, pledge_data, fund_data, username=""):
    try:
        _log(job, f"📡 正在连接 {model_name}...")
        time.sleep(0.6)
        _log(job, f"👥 分析 {name} 股东结构...")
        time.sleep(0.5)
        _log(job, "🔍 联网搜索最新减持/增持公告、解禁信息...")
        time.sleep(0.4)
        _log(job, "🏛️ 分析机构持仓变动趋势...")
        time.sleep(0.4)
        _log(job, "⚠️ 评估股权质押风险...")
        p, s = build_holders_prompt(name, tscode, info, holders_data,
                                     pledge_data, fund_data)
        time.sleep(0.4)
        _log(job, "🤖 AI 正在分析股东动向，通常需要 15~30 秒...")
        result, err = call_ai(client, cfg, p, system=s, max_tokens=8000, username=username)
        if err:
            _log(job, f"❌ 股东分析失败：{err}")
            job["result"] = f"⚠️ 股东分析失败：{err}"
            job["error"] = err
            job["status"] = "done"
            return
        _log(job, "📝 整理股东分析结论...")
        time.sleep(0.3)
        _log(job, "✅ 股东/机构动向分析完成！")
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        _log(job, f"❌ 异常：{e}")
        job["result"] = f"⚠️ 股东分析异常：{e}"
        job["status"] = "done"
