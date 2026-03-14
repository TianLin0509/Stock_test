"""Tab 1: 📊 智能分析 — 从 streamlit_app.py 提取"""

import streamlit as st
import pandas as pd

from config import CORE_KEYS, DEEP_KEYS, ALL_ANALYSIS_KEYS
from analysis.runner import (
    get_jobs, start_analysis, is_running, is_done, any_running,
)
from ui.results import (
    _show_analysis_result, _show_job_progress,
    _show_similarity_section, render_radar_section,
)
from ui.charts import render_kline, render_valuation_bands
from data.tushare_client import to_code6


def _show_stock_overview_basic():
    """显示股票概览：仅指标卡片"""
    name = st.session_state["stock_name"]
    ts_code = st.session_state["stock_code"]
    info = st.session_state.get("stock_info", {})

    st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")
    metrics = [
        ("最新价", info.get("最新价(元)", "—")),
        ("市盈率TTM", info.get("市盈率TTM", "—")),
        ("市净率PB", info.get("市净率PB", "—")),
        ("市销率PS", info.get("市销率PS", "—")),
        ("换手率", info.get("换手率(%)", "—")),
        ("行业", info.get("行业", "—")),
    ]
    r1 = st.columns(3)
    for col, (label, val) in zip(r1, metrics[:3]):
        with col: st.metric(label, str(val)[:14])
    r2 = st.columns(3)
    for col, (label, val) in zip(r2, metrics[3:]):
        with col: st.metric(label, str(val)[:14])


def render_analysis_tab(client, cfg_now, selected_model, email_addr):
    """渲染智能分析 Tab 的全部内容"""
    stock_ready = bool(st.session_state.get("stock_name"))
    analyses = st.session_state.get("analyses", {})
    current_user = st.session_state.get("current_user", "")

    # ── active_view 初始化 ────────────────────────────────────
    if "active_view" not in st.session_state:
        st.session_state["active_view"] = "overview"
    active_view = st.session_state["active_view"]

    # ── 操作栏：3 按钮（预期差 / 趋势 / 基本面）──
    _action_cols = st.columns(3)

    core_all_done = stock_ready and all(analyses.get(k) for k in CORE_KEYS)
    core_all_started = stock_ready and all(
        (analyses.get(k) or is_running(st.session_state, k)) for k in CORE_KEYS
    )
    deep_all_done = all(analyses.get(k) for k in DEEP_KEYS)
    deep_any_running = any(is_running(st.session_state, k) for k in DEEP_KEYS)

    # Col 0-2: 核心三项按钮
    _view_map = [
        (0, "expectation", "预期差", "🔍"),
        (1, "trend", "趋势", "📈"),
        (2, "fundamentals", "基本面", "📋"),
    ]
    for col_idx, key, label, icon in _view_map:
        with _action_cols[col_idx]:
            running = is_running(st.session_state, key)
            done = bool(analyses.get(key))
            _btn_type = "primary" if active_view == key else "secondary"

            if running:
                _btn_label = f"⏳ {label}"
            elif done:
                _btn_label = f"✅ {label}"
            else:
                _btn_label = f"{icon} {label}"

            query = st.session_state.get("query_input", "")
            if st.button(_btn_label, type=_btn_type,
                         use_container_width=True, key=f"btn_{key}",
                         disabled=(not stock_ready and not query)):
                st.session_state["active_view"] = key
                if not done and not running:
                    if not stock_ready and query:
                        # 需要先解析股票 — 委托回主模块
                        st.session_state["_pending_resolve"] = query
                        st.session_state["_pending_analysis_key"] = key
                        st.rerun()
                    if client and stock_ready:
                        start_analysis(st.session_state, key, client, cfg_now,
                                       selected_model)
                st.session_state["_skip_poll_sleep"] = True
                st.session_state["_fast_rerun"] = True
                st.rerun()

    # 深度分析按钮：仅在核心三项完成后显示（独立行）
    if core_all_done or deep_any_running or deep_all_done:
        if deep_any_running:
            st.button("⏳ 深度分析进行中…", disabled=True,
                      use_container_width=True, key="btn_deep")
        elif deep_all_done:
            st.button("✅ 舆情+板块+股东 深度分析已完成", disabled=True,
                      use_container_width=True, key="btn_deep")
        else:
            if st.button("🔬 开始深度分析（舆情+板块+股东）", use_container_width=True,
                         key="btn_deep", type="primary"):
                if client:
                    for dk in DEEP_KEYS:
                        if not analyses.get(dk) and not is_running(st.session_state, dk):
                            start_analysis(st.session_state, dk, client, cfg_now,
                                           selected_model)
                    st.session_state["_auto_sim"] = True
                st.session_state["_skip_poll_sleep"] = True
                st.session_state["_fast_rerun"] = True
                st.rerun()

    # ── 紧凑状态栏 ──────────────────────────────────────────
    active_view = st.session_state.get("active_view", "overview")
    _name_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面"}

    if stock_ready and (any(analyses.get(k) for k in CORE_KEYS)
                       or any(is_running(st.session_state, k) for k in CORE_KEYS)):
        _status_parts = []
        for k in CORE_KEYS:
            if analyses.get(k):
                _status_parts.append(f'<span style="color:#16a34a;">✅{_name_map[k]}</span>')
            elif is_running(st.session_state, k):
                _status_parts.append(
                    f'<span style="color:#6366f1;">'
                    f'⏳{_name_map[k]}分析中<span class="loading-dots"></span></span>'
                )
            else:
                _status_parts.append(f'<span style="color:#9ca3af;">⬜{_name_map[k]}</span>')

        _deep_map = {"sentiment": "舆情", "sector": "板块", "holders": "股东"}
        if deep_any_running or any(analyses.get(k) for k in DEEP_KEYS):
            for dk in DEEP_KEYS:
                if analyses.get(dk):
                    _status_parts.append(f'<span style="color:#16a34a;">✅{_deep_map[dk]}</span>')
                elif is_running(st.session_state, dk):
                    _status_parts.append(
                        f'<span style="color:#6366f1;">'
                        f'⏳{_deep_map[dk]}分析中<span class="loading-dots"></span></span>'
                    )

        _status_line = " &nbsp;|&nbsp; ".join(_status_parts)
        st.markdown(
            f'<div style="font-size:0.75rem;color:#6b7280;margin:4px 0;">{_status_line}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── 主内容区：按 active_view 条件渲染 ────────────────────
    if not stock_ready:
        st.info("请在上方输入股票代码/名称，点击「开始分析」")
    else:
        if active_view == "overview":
            _render_overview(client, cfg_now, analyses, core_all_done, current_user)
        elif active_view == "expectation":
            _render_expectation(analyses)
        elif active_view == "trend":
            _render_trend(analyses)
        elif active_view == "fundamentals":
            _render_fundamentals(analyses)

    # ── 邮件推送（所有视图共享）──────────────────────────
    if email_addr and analyses and not any_running(st.session_state):
        has_any = any(analyses.get(k) for k in ALL_ANALYSIS_KEYS)
        if has_any:
            st.markdown("---")
            if st.button("📧 发送分析报告到邮箱", key="send_email"):
                with st.spinner("正在发送..."):
                    from utils.email_sender import send_analysis_email
                    ok, msg = send_analysis_email(
                        email_addr,
                        st.session_state.get("stock_name", ""),
                        to_code6(st.session_state.get("stock_code", "")),
                        st.session_state.get("stock_info", {}),
                        analyses,
                        st.session_state.get("moe_results", {}),
                        st.session_state.get("selected_model", ""),
                    )
                    if ok:
                        st.success(f"✅ 已发送至 {email_addr}")
                    else:
                        st.error(msg)


# ══════════════════════════════════════════════════════════════════════════════
# 各视图的渲染函数
# ══════════════════════════════════════════════════════════════════════════════

def _render_overview(client, cfg_now, analyses, core_all_done, current_user):
    """overview 视图（基本指标 + 归档恢复 + 雷达）"""
    _show_stock_overview_basic()
    st.markdown("---")

    # 归档缓存检查（无分析结果时自动恢复 / 加载他人结果）
    from utils.archive import find_recent, find_today_others, load_archive

    if not analyses:
        _stock_code = st.session_state["stock_code"]

        # 用 session_state 缓存归档查询结果（Phase 1.3）
        _archive_gen = st.session_state.get("_archive_gen", 0)
        _cache = st.session_state.get("_archive_lookup", {})
        if _cache.get("gen") != _archive_gen or _cache.get("code") != _stock_code:
            _recent = find_recent(_stock_code)
            _others = find_today_others(_stock_code, exclude_user=current_user)
            st.session_state["_archive_lookup"] = {
                "gen": _archive_gen, "code": _stock_code,
                "recent": _recent, "others": _others,
            }
        else:
            _recent = _cache.get("recent")
            _others = _cache.get("others", [])

        # 1) 自动恢复
        if _recent:
            _recent_data = load_archive(_recent["file"])
            if _recent_data and _recent_data.get("analyses"):
                st.session_state["analyses"] = _recent_data["analyses"]
                if _recent_data.get("moe_results"):
                    st.session_state["moe_results"] = {
                        **_recent_data["moe_results"], "done": True,
                    }
                _ts_short = _recent.get("ts", "")[11:16]
                _from_user = _recent.get("username", "")
                st.session_state["_shared_from"] = (
                    f"{_from_user} · {_recent.get('model', '')} · {_ts_short}"
                )
                st.rerun()

        # 2) 今日其他用户的归档（手动加载）
        if _others:
            for sh in _others:
                _ts_short = sh.get("ts", "")[11:16]
                _lbl_map = {
                    "expectation": "预期差", "trend": "趋势解读",
                    "fundamentals": "基本面", "sentiment": "舆情",
                    "sector": "板块", "holders": "股东",
                }
                keys_str = "、".join(
                    _lbl_map.get(k, k) for k in sh.get("analyses_done", [])
                )
                moe_tag = " + 六方会谈" if sh.get("has_moe") else ""
                st.info(
                    f"📦 **{sh['username']}** 于 {_ts_short} 已用 "
                    f"{sh.get('model', '')} 分析过此股票（{keys_str}{moe_tag}）"
                )
                if st.button(
                    f"📥 加载 {sh['username']} 的分析结果（免费）",
                    key=f"load_arch_{sh['username']}_{sh.get('model', '')}",
                ):
                    _arch_data = load_archive(sh["file"])
                    if _arch_data:
                        st.session_state["analyses"] = _arch_data.get("analyses", {})
                        if _arch_data.get("moe_results"):
                            st.session_state["moe_results"] = {
                                **_arch_data["moe_results"], "done": True,
                            }
                        st.session_state["_shared_from"] = (
                            f"{sh['username']} · {sh.get('model', '')} · {_ts_short}"
                        )
                        st.session_state["_archive_gen"] = st.session_state.get("_archive_gen", 0) + 1
                        st.rerun()
            st.markdown("---")

    # 缓存来源标注
    shared_from = st.session_state.get("_shared_from")
    if shared_from and analyses:
        st.caption(f"📦 当前结果来自缓存：{shared_from}（可重新分析覆盖）")

    from ai.client import get_ai_client
    _, _, ai_err = get_ai_client(st.session_state.get("selected_model", ""))
    if ai_err:
        st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}，请在左侧切换其他模型。
</div>""", unsafe_allow_html=True)

    if core_all_done:
        render_radar_section()


def _render_expectation(analyses):
    """expectation 视图"""
    _has_deep_exp = analyses.get("sentiment") or is_running(st.session_state, "sentiment")
    if is_running(st.session_state, "expectation"):
        _show_job_progress("expectation", "预期差分析")
    elif analyses.get("expectation"):
        name = st.session_state.get("stock_name", "")
        if _has_deep_exp:
            with st.expander(f"🔍 {name} · 预期差分析结果", expanded=False):
                st.markdown(analyses["expectation"])
        else:
            st.markdown(f"#### 🔍 {name} · 预期差分析结果")
            with st.container(border=True):
                st.markdown(analyses["expectation"])
    else:
        st.info("预期差分析尚未执行，点击上方按钮开始分析")
    # 深度舆情追加
    if analyses.get("sentiment"):
        st.markdown("---")
        name = st.session_state.get("stock_name", "")
        st.markdown(f"#### 📣 {name} · 舆情情绪分析（深度）")
        with st.container(border=True):
            st.markdown(analyses["sentiment"])
    elif is_running(st.session_state, "sentiment"):
        _show_job_progress("sentiment", "舆情情绪分析")


def _render_trend(analyses):
    """trend 视图（K线图 + 趋势解读 + K线匹配）"""
    _t_name = st.session_state.get("stock_name", "")
    _t_code = st.session_state.get("stock_code", "")
    _t_df = st.session_state.get("price_df", pd.DataFrame())
    _has_deep_trend = (st.session_state.get("_auto_sim")
                       or st.session_state.get("similarity_results"))

    if is_running(st.session_state, "trend"):
        if not _t_df.empty:
            render_kline(_t_df, _t_name, _t_code)
            st.markdown("---")
        _show_job_progress("trend", "趋势解读分析")
    elif analyses.get("trend"):
        if _has_deep_trend:
            with st.expander(f"📈 {_t_name} · 趋势解读结果（含K线图）", expanded=False):
                if not _t_df.empty:
                    render_kline(_t_df, _t_name, _t_code)
                    st.markdown("---")
                st.markdown(analyses["trend"])
        else:
            if not _t_df.empty:
                render_kline(_t_df, _t_name, _t_code)
                st.markdown("---")
            st.markdown(f"#### 📈 {_t_name} · 趋势解读结果")
            with st.container(border=True):
                st.markdown(analyses["trend"])
    else:
        if not _t_df.empty:
            render_kline(_t_df, _t_name, _t_code)
            st.markdown("---")
        st.info("趋势解读尚未执行，点击上方按钮开始分析")

    if _has_deep_trend:
        st.markdown("---")
        _show_similarity_section(
            st.session_state.get("stock_name", ""),
            st.session_state.get("stock_code", ""),
        )


def _render_fundamentals(analyses):
    """fundamentals 视图（估值分位 + 基本面 + 板块 + 股东）"""
    _f_name = st.session_state.get("stock_name", "")
    _f_val_df = st.session_state.get("valuation_df", pd.DataFrame())
    _has_deep_fund = (analyses.get("sector") or analyses.get("holders")
                      or is_running(st.session_state, "sector")
                      or is_running(st.session_state, "holders"))

    if is_running(st.session_state, "fundamentals"):
        if not _f_val_df.empty:
            st.markdown(f"#### 📊 {_f_name} · 估值历史分位")
            render_valuation_bands(_f_val_df, _f_name)
            st.markdown("---")
        _show_job_progress("fundamentals", "基本面分析")
    elif analyses.get("fundamentals"):
        if _has_deep_fund:
            with st.expander(f"📋 {_f_name} · 基本面分析结果（含估值分位）", expanded=False):
                if not _f_val_df.empty:
                    st.markdown(f"#### 📊 估值历史分位")
                    render_valuation_bands(_f_val_df, _f_name)
                    st.markdown("---")
                st.markdown(analyses["fundamentals"])
        else:
            if not _f_val_df.empty:
                st.markdown(f"#### 📊 {_f_name} · 估值历史分位")
                render_valuation_bands(_f_val_df, _f_name)
                st.markdown("---")
            st.markdown(f"#### 📋 {_f_name} · 基本面分析结果")
            with st.container(border=True):
                st.markdown(analyses["fundamentals"])
    else:
        if not _f_val_df.empty:
            st.markdown(f"#### 📊 {_f_name} · 估值历史分位")
            render_valuation_bands(_f_val_df, _f_name)
            st.markdown("---")
        st.info("基本面分析尚未执行，点击上方按钮开始分析")

    # 深度板块追加
    if analyses.get("sector"):
        st.markdown("---")
        st.markdown(f"#### 🏭 {_f_name} · 板块联动分析（深度）")
        with st.container(border=True):
            st.markdown(analyses["sector"])
    elif is_running(st.session_state, "sector"):
        _show_job_progress("sector", "板块联动分析")
    # 深度股东追加
    if analyses.get("holders"):
        st.markdown("---")
        st.markdown(f"#### 👥 {_f_name} · 股东/机构动向（深度）")
        with st.container(border=True):
            st.markdown(analyses["holders"])
    elif is_running(st.session_state, "holders"):
        _show_job_progress("holders", "股东/机构动向分析")
