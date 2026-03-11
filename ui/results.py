"""分析结果展示 — K线常驻 + 五个独立功能按钮（含自由提问）"""

import streamlit as st
import pandas as pd
from ui.charts import render_kline, render_similar_case
from analysis.moe import run_moe, MOE_ROLES
from ai.client import call_ai, call_ai_stream
from ai.context import build_analysis_context
from ai.prompts import (
    build_expectation_prompt,
    build_trend_prompt,
    build_fundamentals_prompt,
)
from data.tushare_client import price_summary
from data.similarity import load_history, find_similar


def _stream_with_fallback(client, cfg, prompt, system, max_tokens, label):
    """流式输出，如果返回空则自动回退非流式"""
    text = st.write_stream(
        call_ai_stream(client, cfg, prompt, system=system, max_tokens=max_tokens)
    )
    if text and text.strip():
        return text
    st.caption(f"⏳ {label} 流式未返回内容，正在重试...")
    fallback_text, err = call_ai(
        client, cfg, prompt, system=system, max_tokens=max_tokens,
    )
    if err:
        st.markdown(
            f'<div class="status-banner warn">⚠️ {label}失败：{err}</div>',
            unsafe_allow_html=True,
        )
        return f"⚠️ {label}失败：{err}"
    if fallback_text:
        st.markdown(fallback_text)
    return fallback_text or ""


def show_results(client, cfg, model_name: str):
    """展示 K 线 + 五个独立功能模块"""
    analyses = st.session_state.get("analyses", {})
    name     = st.session_state.get("stock_name", "")
    tscode   = st.session_state.get("stock_code", "")
    df       = st.session_state.get("price_df", pd.DataFrame())
    info     = st.session_state.get("stock_info", {})

    has_client = client is not None

    # ── K线图（始终展示，不花 Token）──────────────────────────────────────
    render_kline(df, name, tscode)

    # ── 历史相似走势匹配（纯数据驱动，不花 Token）──────────────────────────
    _render_similarity_section(df, tscode, name)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════
    # 五个功能按钮：四个分析 + 自由提问
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("#### 🧠 AI 深度分析（按需点击，独立运行）")

    c1, c2, c3, c4, c5 = st.columns(5)

    exp_done   = bool(analyses.get("expectation"))
    trend_done = bool(analyses.get("trend"))
    fund_done  = bool(analyses.get("fundamentals"))
    moe_done   = bool(st.session_state.get("moe_results", {}).get("done"))

    with c1:
        run_exp = st.button(
            "✅ 预期差已完成" if exp_done else "🔍 预期差分析",
            use_container_width=True, disabled=not has_client,
        )
    with c2:
        run_trend = st.button(
            "✅ 趋势已完成" if trend_done else "📈 K线趋势",
            use_container_width=True, disabled=not has_client,
        )
    with c3:
        run_fund = st.button(
            "✅ 基本面已完成" if fund_done else "📋 基本面",
            use_container_width=True, disabled=not has_client,
        )
    with c4:
        run_moe_btn = st.button(
            "✅ 辩论已完成" if moe_done else "🎯 MoE辩论",
            use_container_width=True, disabled=not has_client,
        )
    with c5:
        run_qa = st.button(
            "💬 自由提问",
            use_container_width=True, disabled=not has_client,
        )

    if not has_client:
        st.caption("⚠️ 当前模型 API Key 未配置，请在左侧切换已配置的模型")

    # ── 执行：预期差分析 ──────────────────────────────────────────────────
    if run_exp and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 🔍 预期差分析中（联网搜索最新资讯）...
</div>""", unsafe_allow_html=True)
        p, s = build_expectation_prompt(name, tscode, info)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "预期差分析")
        analyses["expectation"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 预期差分析完成！")

    # ── 执行：趋势分析 ───────────────────────────────────────────────────
    if run_trend and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 📈 趋势研判中...
</div>""", unsafe_allow_html=True)
        psmry = price_summary(df)
        cap    = st.session_state.get("stock_cap", "")
        dragon = st.session_state.get("stock_dragon", "")
        p, s = build_trend_prompt(name, tscode, psmry, cap, dragon)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "趋势研判")
        analyses["trend"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 趋势研判完成！")

    # ── 执行：基本面分析 ──────────────────────────────────────────────────
    if run_fund and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 📋 基本面剖析中...
</div>""", unsafe_allow_html=True)
        fin = st.session_state.get("stock_fin", "")
        p, s = build_fundamentals_prompt(name, tscode, info, fin)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "基本面剖析")
        analyses["fundamentals"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 基本面剖析完成！")

    # ── 执行：MoE 辩论裁决 ────────────────────────────────────────────────
    if run_moe_btn and has_client:
        missing = []
        if not exp_done:   missing.append("🔍 预期差分析")
        if not trend_done: missing.append("📈 趋势分析")
        if not fund_done:  missing.append("📋 基本面分析")

        if missing:
            st.markdown("---")
            missing_str = "、".join(missing)
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>MoE 辩论需要前三项分析结果</strong><br>
  请先完成：{missing_str}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown("---")
            st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 🎯 MoE 四方辩论裁决中...
</div>""", unsafe_allow_html=True)
            run_moe(client, cfg, name, tscode, analyses)

    # ── 执行：自由提问 ────────────────────────────────────────────────────
    if run_qa and has_client:
        _render_free_question(client, cfg, model_name, name, tscode, info, analyses)

    # ── 已完成的分析结果展示 ──────────────────────────────────────────────
    _show_completed_results(analyses)


# ══════════════════════════════════════════════════════════════════════════════
# 自由提问
# ══════════════════════════════════════════════════════════════════════════════

def _render_free_question(client, cfg, model_name, name, tscode, info, analyses):
    """自由提问交互区域"""
    st.markdown("---")
    st.markdown(f"#### 💬 自由提问 · {name}")

    # 显示已有分析上下文状态
    done_modules = []
    if analyses.get("expectation"):  done_modules.append("预期差")
    if analyses.get("trend"):        done_modules.append("趋势")
    if analyses.get("fundamentals"): done_modules.append("基本面")
    if st.session_state.get("moe_results", {}).get("done"):
        done_modules.append("MoE辩论")

    if done_modules:
        st.caption(f"📎 已有分析上下文：{' · '.join(done_modules)}（将作为参考背景）")
    else:
        st.caption("📎 尚无已完成的分析，AI 将基于股票基本信息和联网搜索回答")

    # 输入框
    question = st.text_area(
        "输入你的问题",
        placeholder=f"例如：{name}近期和华为的合作还有炒作预期吗？\n"
                    f"例如：这只股票适合长期持有吗？\n"
                    f"例如：帮我分析下{name}的股东结构有没有风险",
        height=100,
        key="free_question_input",
        label_visibility="collapsed",
    )

    if st.button("🚀 提交问题", type="primary", key="submit_free_question"):
        if not question or not question.strip():
            st.warning("请输入你的问题")
            return

        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 💬 正在回答你的问题...
</div>""", unsafe_allow_html=True)

        # 构建上下文
        context = build_analysis_context(analyses, max_per_module=12)

        # 提取关键指标
        metrics_parts = []
        for k in ["最新价(元)", "市盈率TTM", "市净率PB", "行业"]:
            v = info.get(k, "")
            if v and str(v) != "N/A":
                metrics_parts.append(f"{k}={v}")
        metrics_line = " | ".join(metrics_parts) if metrics_parts else "暂无"

        system = (
            f"你是一位专业的A股投资顾问，正在为用户分析 {name}（{tscode}）。"
            f"用户可能问任何和这只股票相关的问题。"
            f"\n\n你的回答原则："
            f"\n- 以用户的问题为核心，直接回答用户想知道的内容"
            f"\n- 如果已有分析结果与问题相关，引用其中的具体结论"
            f"\n- 如果问题涉及最新信息，通过联网搜索获取"
            f"\n- 回答要具体、有数据支撑，避免空泛"
            f"\n- 涉及操作建议时要附带风险提示"
        )

        prompt = f"""## 股票：{name}（{tscode}）
## 关键指标：{metrics_line}

## 已有分析上下文（仅供参考，以用户问题为主）
{context}

---

## 🎯 用户问题（请重点回答这个问题）
{question}

请用中文详细回答上述问题。如果问题涉及最新信息，请通过联网搜索获取。
"""
        result = _stream_with_fallback(client, cfg, prompt, system, 8000, "自由提问")

        # 保存提问历史
        qa_history = st.session_state.get("qa_history", [])
        qa_history.append({"question": question, "answer": result})
        st.session_state["qa_history"] = qa_history


# ══════════════════════════════════════════════════════════════════════════════
# 结果展示
# ══════════════════════════════════════════════════════════════════════════════

def _show_completed_results(analyses: dict):
    """以 Tab 页展示已完成的分析结果"""
    has_any = (
        analyses.get("expectation") or analyses.get("trend")
        or analyses.get("fundamentals")
        or st.session_state.get("moe_results", {}).get("done")
        or st.session_state.get("qa_history")
    )

    if not has_any:
        return

    st.markdown("---")
    st.markdown("#### 📊 分析结果")

    tabs = []
    tab_keys = []
    if analyses.get("expectation"):
        tabs.append("🔍 预期差")
        tab_keys.append("expectation")
    if analyses.get("trend"):
        tabs.append("📈 趋势")
        tab_keys.append("trend")
    if analyses.get("fundamentals"):
        tabs.append("📋 基本面")
        tab_keys.append("fundamentals")
    if st.session_state.get("moe_results", {}).get("done"):
        tabs.append("🎯 MoE辩论")
        tab_keys.append("moe")
    if st.session_state.get("qa_history"):
        tabs.append("💬 提问记录")
        tab_keys.append("qa")

    if not tabs:
        return

    tab_objs = st.tabs(tabs)

    for tab_obj, key in zip(tab_objs, tab_keys):
        with tab_obj:
            if key == "moe":
                _render_moe_results()
            elif key == "qa":
                _render_qa_history()
            else:
                content = analyses.get(key, "")
                if content:
                    with st.container(border=True):
                        st.markdown(content)


def _render_moe_results():
    """渲染 MoE 辩论结果"""
    moe = st.session_state.get("moe_results", {})
    if not moe.get("done"):
        return

    for role in MOE_ROLES:
        text = moe["roles"].get(role["key"], "")
        st.markdown(f"""<div class="role-card {role['css']}">
  <div class="role-badge">{role['badge']}</div>
  <div class="role-content">{text}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""<div class="role-card r-ceo">
  <div class="role-badge">👔 首席执行官 · 最终裁决</div>
  <div class="role-content">{moe['ceo']}</div>
</div>""", unsafe_allow_html=True)


def _render_qa_history():
    """渲染自由提问历史记录"""
    qa_history = st.session_state.get("qa_history", [])
    if not qa_history:
        return

    for i, item in enumerate(reversed(qa_history), 1):
        st.markdown(f"**🙋 问题 {len(qa_history) - i + 1}：** {item['question']}")
        with st.container(border=True):
            st.markdown(item["answer"])
        if i < len(qa_history):
            st.markdown("")


# ══════════════════════════════════════════════════════════════════════════════
# 历史相似走势
# ══════════════════════════════════════════════════════════════════════════════

def _render_similarity_section(df: pd.DataFrame, tscode: str, name: str):
    """历史相似走势匹配区域"""
    history = load_history()
    has_history = not history.empty

    with st.expander("🔎 历史相似走势匹配（全市场搜索，不消耗 Token）", expanded=False):
        if not has_history:
            st.warning(
                "⚠️ 尚未构建历史数据库。请先运行离线脚本：\n\n"
                "```bash\n"
                "export TUSHARE_TOKEN='你的token'\n"
                "export TUSHARE_URL='你的url'\n"
                "python data/build_history.py\n"
                "```\n\n"
                "构建完成后将 `data/history/all_daily.parquet` 放入项目目录即可。"
            )
            return

        if df.empty:
            st.info("需要先查询股票获取 K 线数据")
            return

        stock_count = history["ts_code"].nunique()
        date_range  = f"{history['trade_date'].min()} ~ {history['trade_date'].max()}"
        st.caption(f"📊 历史数据库：{stock_count} 只股票 · {date_range}")

        col_k, col_btn = st.columns([1, 1])
        with col_k:
            k_days = st.selectbox(
                "匹配窗口天数",
                options=[3, 5, 10, 20],
                index=1,
                key="sim_k_days",
            )
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            run_sim = st.button("🚀 搜索相似走势", type="primary",
                                use_container_width=True, key="run_similarity")

        if run_sim:
            if len(df) < k_days:
                st.warning(f"K线数据不足 {k_days} 天，请减少窗口天数")
                return

            with st.spinner(f"🔍 在 {stock_count} 只股票中搜索最近 {k_days} 天的相似走势..."):
                results = find_similar(
                    target_df=df,
                    k_days=k_days,
                    top_n=3,
                    context_days=10,
                    exclude_code=tscode,
                )

            if not results:
                st.info("未找到足够相似的历史走势（相似度阈值 > 30%）")
                return

            st.session_state["similarity_results"] = results
            st.success(f"✅ 找到 {len(results)} 个相似走势案例！")

        saved = st.session_state.get("similarity_results", [])
        if saved:
            st.markdown("---")
            for i, case in enumerate(saved, 1):
                render_similar_case(case, i)
                if i < len(saved):
                    st.markdown("")
