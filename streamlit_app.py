#!/usr/bin/env python3
"""
📈 A股智能投研助手 v4
Multi-Model + Tushare · 模块化架构
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

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
    get_capital_flow, get_dragon_tiger,
)
from ai.client import get_ai_client

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
**① 选择分析模型**

**② 输入股票代码或名称**
> 例：`600519` 或 `贵州茅台`

**③ 点击「查询」获取数据**

**④ 按需点击分析按钮**
> 🔍 预期差 · 📈 趋势 · 📋 基本面
> 独立分析，节省 Token

**⑤ 「MoE辩论」**
> 需先完成前三项分析
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

    # ── 搜索栏 + 查询按钮 ─────────────────────────────────────────────────
    query = st.text_input(
        "搜索股票", label_visibility="collapsed",
        placeholder="🔍  输入股票代码（如 000858）或名称（如 五粮液）…",
        key="query_input",
    )
    search_btn = st.button("🔍 查询股票", type="primary", use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    # 第一步：查询 → 获取 Tushare 数据（不花 Token）
    # ══════════════════════════════════════════════════════════════════════
    if search_btn and query:
        if not ts_ok():
            st.markdown("""<div class="status-banner error">
  ❌ <strong>Tushare 数据源不可用</strong>，无法获取行情数据。
</div>""", unsafe_allow_html=True)
            st.stop()

        # 清除上一只股票的结果
        for k in ["analyses", "moe_results", "stock_fin",
                   "stock_cap", "stock_dragon"]:
            st.session_state.pop(k, None)
        st.session_state["analyses"] = {}

        with st.spinner("🔍 解析股票中..."):
            ts_code, name, resolve_warn = resolve_stock(query)
        if resolve_warn:
            st.markdown(f'<div class="status-banner warn">⚠️ {resolve_warn}</div>',
                        unsafe_allow_html=True)

        st.session_state["stock_code"] = ts_code
        st.session_state["stock_name"] = name

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
            st.session_state["stock_fin"] = fin

            st.write("▶ 主力资金流向...")
            cap, e = get_capital_flow(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_cap"] = cap

            st.write("▶ 龙虎榜...")
            dragon, e = get_dragon_tiger(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_dragon"] = dragon

            s.update(label="✅ 数据获取完成！", state="complete")

        if data_errors:
            errs_text = " | ".join(data_errors[:3])
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>：{errs_text}
</div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # 第二步：展示数据 + 四个独立分析按钮
    # ══════════════════════════════════════════════════════════════════════
    if st.session_state.get("stock_name"):
        ts_code = st.session_state["stock_code"]
        name = st.session_state["stock_name"]
        info = st.session_state.get("stock_info", {})

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

        # ── 获取 AI 客户端 ────────────────────────────────────────────────
        client, cfg_now, ai_err = get_ai_client(selected_model)
        if ai_err:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}<br>
  K线图可正常查看，AI 分析需切换其他模型。
</div>""", unsafe_allow_html=True)

        # ── 展示面板（K线 + 四个分析按钮）─────────────────────────────────
        show_results(client, cfg_now, selected_model)


if __name__ == "__main__":
    main()
