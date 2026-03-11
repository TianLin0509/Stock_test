"""分析结果展示 — Tab 页渲染"""

import streamlit as st
import pandas as pd
from ui.charts import render_kline
from analysis.moe import run_moe, MOE_ROLES


def show_results(client, cfg):
    r      = st.session_state.get("analyses", {})
    name   = st.session_state.get("stock_name", "")
    tscode = st.session_state.get("stock_code", "")
    df     = st.session_state.get("price_df", pd.DataFrame())

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 预期差分析", "📈 K线 & 趋势", "📋 基本面", "🎯 MoE 辩论裁决",
    ])

    with tab1:
        content = r.get("expectation", "")
        if content:
            with st.container(border=True):
                st.markdown(content)
        else:
            st.info("点击「开始分析」后，预期差分析结果将显示在这里。")

    with tab2:
        render_kline(df, name, tscode)
        content = r.get("trend", "")
        if content:
            st.markdown("---")
            with st.container(border=True):
                st.markdown(content)

    with tab3:
        content = r.get("fundamentals", "")
        if content:
            with st.container(border=True):
                st.markdown(content)
        else:
            st.info("基本面分析结果将显示在这里。")

    with tab4:
        moe = st.session_state.get("moe_results", {})
        if moe.get("done"):
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
        else:
            st.info("💡 完成分析后，点击下方按钮启动四方辩论，获取带具体点位的操作结论。")
            st.caption("⚠️ 普通散户的观点将作为**反向指标**，首席执行官会逆向参考。")
            if not r:
                st.warning("请先点击「🚀 开始分析」完成股票分析。")
            elif client:
                if st.button("🎯 启动 MoE 辩论博弈", type="primary"):
                    run_moe(client, cfg, name, tscode, r)
            else:
                st.warning("⚠️ 当前模型 API Key 未配置，暂无法启动辩论。")
