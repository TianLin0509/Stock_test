"""Sidebar 逻辑 — 从 streamlit_app.py 提取"""

import streamlit as st
from config import MODEL_CONFIGS, MODEL_NAMES, ADMIN_USERNAME
from data.tushare_client import get_ts_error


def render_sidebar(current_user: str, on_logout) -> tuple[str, str]:
    """渲染侧边栏，返回 (selected_model, email_addr)"""
    with st.sidebar:
        st.markdown(f"**👤 {current_user}**")
        if st.button("🔄 切换用户", key="logout_btn"):
            on_logout()

        st.markdown("---")
        st.markdown("### 🤖 选择分析模型")
        selected_model = st.selectbox(
            "当前模型", options=MODEL_NAMES, index=3,
            key="selected_model", label_visibility="collapsed",
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
            st.markdown('<div class="model-badge err">⚠️ API Key 待配置</div>',
                        unsafe_allow_html=True)
            st.caption("暂无法使用AI分析，K线图仍可正常查看")

        st.markdown("### 📡 数据源状态")
        ts_error = get_ts_error()
        if not ts_error:
            st.markdown('<div class="model-badge ok">✅ Tushare 连接正常</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="model-badge ok">✅ 备用数据源就绪（akshare / 东方财富）</div>',
                        unsafe_allow_html=True)
            st.caption(f"Tushare 不可用：{ts_error}，已自动切换备用源")

        st.markdown("---")
        st.markdown("### 📖 使用方法")
        st.markdown("""
**① 选择分析模型**

**② 输入股票代码或名称**
> 例：`600519` 或 `贵州茅台`

**③ 点击「查询股票」**

**④ 按需点击分析按钮**
> 可同时启动多个分析，切换查看进度

**⑤ 「自由提问」**
> 针对股票问任何问题
""")

        st.markdown("---")
        st.markdown("### 📧 邮件推送")
        try:
            from utils.email_sender import smtp_configured
            if smtp_configured():
                email_addr = st.text_input("收件邮箱", value="", placeholder="your@email.com",
                                           key="email_input")
                st.caption("分析完成后可一键推送报告到邮箱")
            else:
                st.caption("⚠️ SMTP 未配置")
                st.caption("请在 Secrets 中添加：")
                st.code("SMTP_HOST\nSMTP_PORT\nSMTP_USER\nSMTP_PASS", language=None)
                email_addr = ""
        except Exception:
            st.caption("📧 邮件模块未加载")
            email_addr = ""

        st.markdown("---")
        st.markdown("### 📜 分析历史")
        _cache_key = "_cached_user_data"
        if _cache_key not in st.session_state:
            from utils.user_store import load_user
            st.session_state[_cache_key] = load_user(current_user)
        _udata = st.session_state[_cache_key]
        _hist = _udata.get("history", [])
        if _hist:
            for _entry in reversed(_hist[-10:]):
                _date = _entry.get("ts", "")[:10]
                _sname = _entry.get("stock_name", "")
                _adone = _entry.get("analyses_done", [])
                _tcost = _entry.get("token_cost", 0)
                _tdisp = f"{_tcost/10000:.1f}万" if _tcost >= 10000 else f"{_tcost:,}"
                st.caption(f"{_date} · **{_sname}** ({len(_adone)}项) · {_tdisp} tokens")
        else:
            st.caption("暂无分析记录")

        # ── 管理后台（仅管理员可见）────────────────────────────────────
        if current_user == ADMIN_USERNAME:
            _render_admin_panel()

        st.markdown("---")
        st.markdown("""
<div class="disclaimer">
⚠️ <strong>免责声明</strong><br>
本工具仅供学习研究，不构成任何投资建议。A股市场风险较大，请独立判断，自行承担投资盈亏。
</div>
""", unsafe_allow_html=True)

    return selected_model, email_addr


def _render_admin_panel():
    """管理后台面板"""
    st.markdown("---")
    st.markdown("### 🔧 管理后台")
    if st.button("📊 查看所有用户", key="admin_btn"):
        st.session_state["_show_admin"] = not st.session_state.get("_show_admin", False)
    if st.session_state.get("_show_admin"):
        from utils.user_store import get_all_users_summary, load_user as _admin_load
        all_users = get_all_users_summary()
        if all_users:
            st.markdown(f"**共 {len(all_users)} 位用户**")
            for u in all_users:
                _t = u["total_tokens"]
                _td = f"{_t/10000:.1f}万" if _t >= 10000 else f"{_t:,}"
                _last = u.get("last_login", "")[:10]
                st.caption(
                    f"**{u['username']}** · {_td} tokens · "
                    f"{u['history_count']}次分析 · 最后登录 {_last}"
                )
            _unames = [u["username"] for u in all_users]
            _sel = st.selectbox("查看用户详情", ["--"] + _unames, key="admin_user_sel")
            if _sel != "--":
                _ud = _admin_load(_sel)
                _uh = _ud.get("history", [])
                if _uh:
                    st.markdown(f"**{_sel} 的分析记录（近20条）：**")
                    for _e in reversed(_uh[-20:]):
                        st.caption(
                            f"{_e.get('ts', '')[:16]} · {_e.get('stock_name', '')} "
                            f"· {_e.get('model', '')} · "
                            f"{', '.join(_e.get('analyses_done', []))}"
                        )
                else:
                    st.caption("该用户暂无分析记录")
                _daily = _ud.get("token_usage", {}).get("daily", {})
                if _daily:
                    st.markdown("**每日Token用量：**")
                    for _day in sorted(_daily.keys(), reverse=True)[:7]:
                        _dv = _daily[_day]
                        st.caption(f"{_day} · {_dv.get('total', 0):,} tokens")
        else:
            st.caption("暂无用户数据")

        st.markdown("---")
        from utils.archive import get_archive_stats
        _astats = get_archive_stats()
        st.markdown(
            f"**📦 分析归档：** {_astats['count']} 条 · {_astats['size_mb']} MB"
        )
        st.caption("每日12:00自动备份到GitHub + 邮件")
        if st.button("⚡ 立即备份", key="manual_backup"):
            with st.spinner("正在备份..."):
                from utils.backup import run_daily_backup
                _bresults = run_daily_backup()
                for _br in _bresults:
                    st.caption(_br)
