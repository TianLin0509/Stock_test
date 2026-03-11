"""分析结果展示 — K线常驻 + 四个独立分析按钮"""

import streamlit as st
import pandas as pd
from ui.charts import render_kline
from analysis.moe import run_moe, MOE_ROLES
from ai.client import call_ai, call_ai_stream
from ai.prompts import (
    build_expectation_prompt,
    build_trend_prompt,
    build_fundamentals_prompt,
)
from data.tushare_client import price_summary


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
    """展示 K 线 + 四个独立分析模块"""
    analyses = st.session_state.get("analyses", {})
    name     = st.session_state.get("stock_name", "")
    tscode   = st.session_state.get("stock_code", "")
    df       = st.session_state.get("price_df", pd.DataFrame())
    info     = st.session_state.get("stock_info", {})

    has_client = client is not None

    # ── K线图（始终展示，不花 Token）──────────────────────────────────────
    render_kline(df, name, tscode)

    st.markdown("---")

    # ── 四个分析按钮 ──────────────────────────────────────────────────────
    st.markdown("#### 🧠 AI 深度分析（按需点击，独立运行）")

    c1, c2, c3, c4 = st.columns(4)

    exp_done   = bool(analyses.get("expectation"))
    trend_done = bool(analyses.get("trend"))
    fund_done  = bool(analyses.get("fundamentals"))
    moe_done   = bool(st.session_state.get("moe_results", {}).get("done"))

    with c1:
        exp_label = "✅ 预期差已完成" if exp_done else "🔍 预期差分析"
        run_exp = st.button(exp_label, use_container_width=True,
                            disabled=not has_client)
    with c2:
        trend_label = "✅ 趋势已完成" if trend_done else "📈 K线趋势分析"
        run_trend = st.button(trend_label, use_container_width=True,
                              disabled=not has_client)
    with c3:
        fund_label = "✅ 基本面已完成" if fund_done else "📋 基本面分析"
        run_fund = st.button(fund_label, use_container_width=True,
                             disabled=not has_client)
    with c4:
        moe_label = "✅ 辩论已完成" if moe_done else "🎯 MoE 辩论裁决"
        run_moe_btn = st.button(moe_label, use_container_width=True,
                                disabled=not has_client)

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

    # ── 已完成的分析结果展示 ──────────────────────────────────────────────
    _show_completed_results(analyses)


def _show_completed_results(analyses: dict):
    """以 Tab 页展示已完成的分析结果"""
    has_any = (analyses.get("expectation") or analyses.get("trend")
               or analyses.get("fundamentals")
               or st.session_state.get("moe_results", {}).get("done"))

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

    if not tabs:
        return

    tab_objs = st.tabs(tabs)

    for tab_obj, key in zip(tab_objs, tab_keys):
        with tab_obj:
            if key == "moe":
                _render_moe_results()
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
