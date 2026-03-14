"""Tab 6: 💬 互动问答 — 从 streamlit_app.py 提取"""

import streamlit as st

from ui.results import _render_free_question


def render_qa_tab(client, cfg_now, selected_model):
    """渲染互动问答 Tab"""
    stock_ready = bool(st.session_state.get("stock_name"))
    analyses = st.session_state.get("analyses", {})

    if not stock_ready:
        st.info("请先在上方输入股票并分析，然后即可自由提问")
    elif not client:
        st.warning("AI 模型不可用，请检查 API Key")
    else:
        _render_free_question(client, cfg_now, selected_model,
                              st.session_state.get("stock_name", ""),
                              st.session_state.get("stock_code", ""),
                              st.session_state.get("stock_info", {}),
                              analyses)
