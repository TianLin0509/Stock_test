#!/usr/bin/env python3
"""
📈 A股智能投研助手 v4
Multi-Model + Tushare · 模块化架构
"""

import streamlit as st

# ── Page Config（必须在最前面）──────────────────────────────────────────────
st.set_page_config(
    page_title="A股投研小助手 🌸",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(
    '<meta name="viewport" content="width=device-width, initial-scale=1.0, '
    'maximum-scale=1.0, user-scalable=no">',
    unsafe_allow_html=True,
)

# ── 内部模块导入 ──────────────────────────────────────────────────────────
from config import MODEL_CONFIGS, MODEL_NAMES
from ui.styles import inject_css
from ui.results import show_results
from data.tushare_client import (
    ts_ok, get_ts_error, resolve_stock, to_code6,
    get_basic_info, get_price_df, get_financial,
    get_capital_flow, get_dragon_tiger, price_summary,
)
from ai.client import get_ai_client, call_ai, call_ai_stream
from ai.prompts import (
    build_expectation_prompt,
    build_trend_prompt,
    build_fundamentals_prompt,
)

# ── 注入全局样式 ──────────────────────────────────────────────────────────
inject_css()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Header ────────────────────────────────────────────────────────────
    st.markdown("""
<div class="app-header">
  <h1>📈 A股智能投研助手</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
</div>
""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🤖 选择分析模型")

        selected_model = st.selectbox(
            "当前模型",
            options=MODEL_NAMES,
            index=0,
            key="selected_model",
            label_visibility="collapsed",
        )
        cfg = MODEL_CONFIGS[selected_model]

        has_key = bool(cfg["api_key"])
        if has_key:
            search_tip = "🌐 联网搜索已开启" if cfg["supports_search"] else "📚 仅内部知识"
            st.markdown(
                f'<div class="model-badge ok">✅ {cfg["note"]} &nbsp;·&nbsp; {search_tip}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="model-badge err">⚠️ API Key 待配置</div>',
                unsafe_allow_html=True,
            )
            st.caption("暂无法使用AI分析，K线图仍可正常查看")

        st.markdown("### 📡 数据源状态")
        if ts_ok():
            st.markdown('<div class="model-badge ok">✅ Tushare 连接正常</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="model-badge err">❌ Tushare 异常</div>',
                        unsafe_allow_html=True)
            st.caption(f"原因：{get_ts_error()}")

        st.markdown("---")
        st.markdown("### 📖 使用方法")
        st.markdown("""
**① 上方选择分析模型**

**② 输入股票代码或名称**
> 例：`600519` 或 `贵州茅台`

**③ 点击「开始分析」**
> 约 1-3 分钟完成分析

**④ 切换标签查看各模块**

**⑤ 「MoE辩论」标签**
> 获取四方辩论 + 操作结论
""")

        st.markdown("---")
        st.markdown("""
<div class="disclaimer">
⚠️ <strong>免责声明</strong><br>
本工具仅供学习研究，不构成任何投资建议。A股市场风险较大，请独立判断，自行承担投资盈亏。
</div>
""", unsafe_allow_html=True)

    # ── Tushare 全局警告 ──────────────────────────────────────────────────
    if not ts_ok():
        st.markdown(f"""<div class="status-banner error">
  ❌ <strong>Tushare 数据源异常</strong>：{get_ts_error()}<br>
  K线图和财务数据将无法显示，请检查网络连接或联系管理员检查 Token。
</div>""", unsafe_allow_html=True)

    # ── 搜索栏 ───────────────────────────────────────────────────────────
    query = st.text_input(
        "搜索股票", label_visibility="collapsed",
        placeholder="🔍  输入股票代码（如 000858）或名称（如 五粮液）…",
        key="query_input",
    )
    col_btn, col_clr, col_spacer = st.columns([1, 1, 3])
    with col_btn:
        start = st.button("🚀 开始分析", type="primary", use_container_width=True)
    with col_clr:
        if st.button("🗑 重置", use_container_width=True):
            for k in ["analyses", "stock_code", "stock_name",
                      "price_df", "stock_info", "moe_results"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── 执行分析 ──────────────────────────────────────────────────────────
    if start and query:
        client, cfg_now, ai_err = get_ai_client(selected_model)

        if ai_err:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}<br>
  K线图将正常显示，AI深度分析跳过。建议在左侧切换其他模型后重试。
</div>""", unsafe_allow_html=True)

        if not ts_ok():
            st.markdown(f"""<div class="status-banner error">
  ❌ <strong>Tushare 数据源不可用</strong>，无法获取行情数据。请检查网络连接。
</div>""", unsafe_allow_html=True)
            st.stop()

        st.session_state.pop("moe_results", None)

        with st.spinner("🔍 解析股票中..."):
            ts_code, name, resolve_warn = resolve_stock(query)
        if resolve_warn:
            st.markdown(f'<div class="status-banner warn">⚠️ {resolve_warn}</div>',
                        unsafe_allow_html=True)

        st.session_state["stock_code"] = ts_code
        st.session_state["stock_name"] = name

        # ── 获取数据 ──────────────────────────────────────────────────────
        data_errors = []

        with st.status(f"📥 正在获取 {name} 的市场数据...", expanded=True) as s:
            st.write("▶ 基本信息 & 估值指标...")
            info, e = get_basic_info(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_info"] = info

            st.write("▶ 日线K线（近140天）...")
            df, e = get_price_df(ts_code)
            if e: data_errors.append(e)
            st.session_state["price_df"] = df

            st.write("▶ 财务指标...")
            fin, e = get_financial(ts_code)
            if e: data_errors.append(e)

            st.write("▶ 主力资金流向...")
            cap, e = get_capital_flow(ts_code)
            if e: data_errors.append(e)

            st.write("▶ 龙虎榜...")
            dragon, e = get_dragon_tiger(ts_code)
            if e: data_errors.append(e)

            s.update(label="✅ 数据获取完成！", state="complete")

        if data_errors:
            errs_text = " | ".join(data_errors[:3])
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>（不影响主要功能）：{errs_text}
</div>""", unsafe_allow_html=True)

        # ── 指标卡片 ──────────────────────────────────────────────────────
        st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")
        metrics = [
            ("最新价", info.get("最新价(元)", "—")),
            ("市盈率TTM", info.get("市盈率TTM", "—")),
            ("市净率PB", info.get("市净率PB", "—")),
            ("市销率PS", info.get("市销率PS", "—")),
            ("换手率", info.get("换手率(%)", "—")),
            ("行业", info.get("行业", "—")),
        ]
        row1 = st.columns(3)
        for col, (label, val) in zip(row1, metrics[:3]):
            with col:
                st.metric(label, str(val)[:14])
        row2 = st.columns(3)
        for col, (label, val) in zip(row2, metrics[3:]):
            with col:
                st.metric(label, str(val)[:14])

        # ── AI 分析（流式 + 回退） ───────────────────────────────────────
        analyses: dict[str, str] = {}
        if client:
            psmry = price_summary(df)

            def stream_with_fallback(prompt, system, max_tokens, label):
                """流式输出，如果返回空则自动回退非流式"""
                text = st.write_stream(
                    call_ai_stream(client, cfg_now, prompt,
                                   system=system, max_tokens=max_tokens)
                )
                if text and text.strip():
                    return text
                st.caption(f"⏳ {label} 流式未返回内容，正在重试...")
                fallback_text, err = call_ai(
                    client, cfg_now, prompt,
                    system=system, max_tokens=max_tokens,
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

            st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{selected_model} 深度分析中</strong> — 每个模块完成后即时展示，无需等待全部完成
</div>""", unsafe_allow_html=True)

            progress_bar = st.progress(0, text="🔍 1/3 预期差分析（联网搜索最新资讯）...")

            # 1/3 预期差
            st.markdown("#### 🔍 预期差分析")
            p1, s1 = build_expectation_prompt(name, ts_code, info)
            analyses["expectation"] = stream_with_fallback(p1, s1, 8000, "预期差分析")
            progress_bar.progress(33, text="✅ 预期差完成 · 📈 2/3 趋势研判中...")

            st.markdown("---")

            # 2/3 趋势
            st.markdown("#### 📈 趋势研判")
            p2, s2 = build_trend_prompt(name, ts_code, psmry, cap, dragon)
            analyses["trend"] = stream_with_fallback(p2, s2, 8000, "趋势研判")
            progress_bar.progress(66, text="✅ 趋势完成 · 📋 3/3 基本面剖析中...")

            st.markdown("---")

            # 3/3 基本面
            st.markdown("#### 📋 基本面剖析")
            p3, s3 = build_fundamentals_prompt(name, ts_code, info, fin)
            analyses["fundamentals"] = stream_with_fallback(p3, s3, 8000, "基本面剖析")
            progress_bar.progress(100, text="🎉 全部分析完成！")

            st.success("✅ 分析完成！下方标签可查看完整结果，进入「MoE辩论裁决」获取操作建议。")
        else:
            st.markdown(f"""<div class="status-banner info">
  ℹ️ <strong>AI分析已跳过</strong>（API Key 未配置）。K线图已在「K线 & 趋势」标签中生成，可供参考。<br>
  请在左侧切换已配置 API Key 的模型，然后重新点击「开始分析」。
</div>""", unsafe_allow_html=True)

        st.session_state["analyses"] = analyses

    # ── 展示结果 ──────────────────────────────────────────────────────────
    if (st.session_state.get("analyses") is not None
            or st.session_state.get("price_df") is not None):
        if not start:
            ts_code = st.session_state.get("stock_code", "")
            name = st.session_state.get("stock_name", "")
            if name:
                st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")

        _, cfg_now, _ = get_ai_client(selected_model)
        client, _, _ = get_ai_client(selected_model)
        show_results(client, cfg_now)


if __name__ == "__main__":
    main()
