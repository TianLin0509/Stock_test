"""Tab 1: 📊 智能分析 — 从 streamlit_app.py 提取"""

import threading
import time as _time
import streamlit as st
import pandas as pd

from config import CORE_KEYS, DEEP_KEYS, ALL_ANALYSIS_KEYS
from analysis.runner import run_analysis_sync
from ui.results import (
    _show_analysis_result,
    _show_similarity_section, render_radar_section,
)
from ui.charts import render_kline, render_valuation_bands
from data.tushare_client import to_code6


def _store_extra_data(extra: dict | None):
    """将趋势分析附带的资金流数据存入 session_state，供信号雷达使用"""
    if not extra:
        return
    cap = extra.get("capital_flow")
    if cap is not None:
        # cap 可能是 DataFrame 或字符串
        import pandas as _pd
        if isinstance(cap, _pd.DataFrame) and not cap.empty:
            st.session_state["capital_flow_df"] = cap
        elif isinstance(cap, str) and len(cap) > 20:
            st.session_state["stock_capital"] = cap
    nb = extra.get("northbound")
    if nb and isinstance(nb, str) and "暂无" not in nb:
        st.session_state["stock_northbound"] = nb
    margin = extra.get("margin")
    if margin and isinstance(margin, str) and "暂无" not in margin:
        st.session_state["stock_margin"] = margin


def _extract_conclusion(text: str, max_chars: int = 800) -> str:
    """从分析全文中提取结论/总结段落，保留 markdown 格式"""
    import re
    # 按优先级尝试匹配结论段落标题
    patterns = [
        r'(#{1,4}\s*.*(?:综合结论|最终结论|总结|操作建议|投资建议).*)',
        r'(#{1,4}\s*.*(?:三情景|概率估计|风险提示).*)',
        r'(#{1,4}\s*.*(?:中线展望|短线展望|趋势研判).*)',
        r'(#{1,4}\s*.*(?:基本面裁决|筛选结论|综合评分).*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # 从匹配位置截取到文末
            start = match.start()
            conclusion = text[start:start + max_chars]
            if len(text) > start + max_chars:
                conclusion += "\n\n..."
            return conclusion

    # 兜底：取最后 max_chars 字符（通常结论在末尾）
    if len(text) > max_chars:
        # 找一个段落分界
        tail = text[-max_chars:]
        newline_pos = tail.find('\n\n')
        if newline_pos > 0 and newline_pos < max_chars // 2:
            tail = tail[newline_pos + 2:]
        return "...\n\n" + tail
    return text


def _show_stock_overview_basic():
    """显示股票概览：仅指标卡片"""
    name = st.session_state["stock_name"]
    ts_code = st.session_state["stock_code"]
    info = st.session_state.get("stock_info", {})

    # 自选股状态按钮
    _title_col, _fav_col = st.columns([5, 1.5])
    with _title_col:
        st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")
    with _fav_col:
        from utils.user_store import get_watchlist, add_to_watchlist, remove_from_watchlist
        _cur_user = st.session_state.get("current_user", "")
        _in_wl = any(item["stock_code"] == ts_code for item in get_watchlist(_cur_user))
        if _in_wl:
            if st.button("➖ 移除自选", key="wl_remove_analysis", use_container_width=True):
                _ok, _msg = remove_from_watchlist(_cur_user, ts_code)
                st.toast(_msg)
                if _ok:
                    st.session_state.pop("_cached_user_data", None)
                    st.rerun()
        else:
            if st.button("➕ 加入自选", key="wl_add_analysis", use_container_width=True):
                _ok, _msg = add_to_watchlist(_cur_user, ts_code, name)
                st.toast(_msg)
                if _ok:
                    st.session_state.pop("_cached_user_data", None)
                    st.rerun()

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


def _extract_session_data():
    """从 session_state 提取分析所需数据（主线程调用）"""
    name = st.session_state.get("stock_name", "")
    tscode = st.session_state.get("stock_code", "")
    info = dict(st.session_state.get("stock_info", {}))
    fin = st.session_state.get("stock_fin", "")
    df = st.session_state.get("price_df", pd.DataFrame())
    if not df.empty:
        df = df.copy()
    username = st.session_state.get("current_user", "")
    return name, tscode, info, fin, df, username


_HEARTBEAT_TIPS = [
    "正在联网搜索最新资讯…",
    "正在整理分析数据…",
    "正在等待 AI 响应…",
    "AI 正在深度思考中…",
    "即将开始输出结果…",
    "AI 还在思考，请耐心等待…",
    "正在综合多维度数据…",
    "分析内容较多，稍等片刻…",
]


def _run_parallel_with_heartbeat(keys, client, cfg_now, selected_model,
                                  status_label, label_map, analyses):
    """并行执行多项分析，带心跳进度输出"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    name, tscode, info, fin, df, username = _extract_session_data()

    with st.status(f"⏳ {status_label}...", expanded=True) as status:
        st.write(f"📡 并行启动 {len(keys)} 项分析（{selected_model}）...")

        # 心跳：每2秒输出进度提示，直到所有任务完成
        _done_event = threading.Event()
        _status_container = st.empty()  # 用于更新心跳消息

        def _heartbeat():
            elapsed = 0
            idx = 0
            while not _done_event.wait(timeout=2):
                elapsed += 2
                tip = _HEARTBEAT_TIPS[min(idx, len(_HEARTBEAT_TIPS) - 1)]
                _status_container.caption(f"⏱️ 已等待 {elapsed}s — {tip}")
                idx += 1

        hb = threading.Thread(target=_heartbeat, daemon=True)
        hb.start()

        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(
                        run_analysis_sync, k, client, cfg_now, selected_model,
                        name, tscode, info, fin, df, username
                    ): k for k in keys
                }
                for fut in as_completed(futures):
                    k = futures[fut]
                    result, err, extra = fut.result()
                    if not err and result:
                        analyses[k] = result
                        st.session_state["analyses"] = analyses
                        _store_extra_data(extra)
                    st.write(f"{'✅' if not err else '❌'} {label_map.get(k, k)} 完成")
        finally:
            _done_event.set()
            _status_container.empty()

        status.update(label=f"✅ {status_label}完成！", state="complete")


def _run_single_analysis(key, label, client, cfg_now, selected_model, analyses):
    """同步执行单个分析并更新 session_state，带心跳"""
    _run_parallel_with_heartbeat(
        [key], client, cfg_now, selected_model,
        label, {key: label}, analyses,
    )


def _run_deep_analysis(client, cfg_now, selected_model, analyses):
    """同步执行深度分析（舆情+板块+股东），带心跳"""
    keys_to_run = [dk for dk in DEEP_KEYS if not analyses.get(dk)]
    if not keys_to_run:
        return
    label_map = {"sentiment": "舆情情绪", "sector": "板块联动", "holders": "股东动向"}
    _run_parallel_with_heartbeat(
        keys_to_run, client, cfg_now, selected_model,
        f"深度分析（{len(keys_to_run)}项）", label_map, analyses,
    )
    st.session_state["_auto_sim"] = True


def render_analysis_tab(client, cfg_now, selected_model, email_addr):
    """渲染智能分析 Tab 的全部内容"""
    stock_ready = bool(st.session_state.get("stock_name"))
    analyses = st.session_state.get("analyses", {})
    current_user = st.session_state.get("current_user", "")

    # 是否有待执行的分析（一键分析 / 单项分析）
    _pending_core = st.session_state.get("_pending_core_analysis", False)
    _pending_single = st.session_state.pop("_pending_single_key", None)
    _is_analyzing = _pending_core or _pending_single is not None

    # ── active_view 初始化 ────────────────────────────────────
    if "active_view" not in st.session_state:
        st.session_state["active_view"] = "overview"
    active_view = st.session_state["active_view"]

    # ── 操作栏：4 按钮（预期差 / 趋势 / 基本面 / 总结）──
    _action_cols = st.columns(4)

    core_all_done = stock_ready and all(analyses.get(k) for k in CORE_KEYS)
    deep_all_done = all(analyses.get(k) for k in DEEP_KEYS)

    # Col 0-2: 核心三项按钮
    _view_map = [
        (0, "expectation", "预期差", "🔍"),
        (1, "trend", "趋势", "📈"),
        (2, "fundamentals", "基本面", "📋"),
    ]
    for col_idx, key, label, icon in _view_map:
        with _action_cols[col_idx]:
            done = bool(analyses.get(key))
            _btn_type = "primary" if active_view == key else "secondary"

            if _is_analyzing and not done:
                _btn_label = f"⏳ {label}"
            elif done:
                _btn_label = f"✅ {label}"
            else:
                _btn_label = f"{icon} {label}"

            query = st.session_state.get("query_input", "")
            # 分析进行中时禁用所有按钮
            _disabled = _is_analyzing or (not stock_ready and not query)
            if st.button(_btn_label, type=_btn_type,
                         use_container_width=True, key=f"btn_{key}",
                         disabled=_disabled):
                st.session_state["active_view"] = key
                if not done:
                    if not stock_ready and query:
                        st.session_state["_pending_resolve"] = query
                        st.session_state["_pending_analysis_key"] = key
                        st.rerun()
                    if client and stock_ready:
                        # 标记待执行，下次 rerun 时在下方执行
                        st.session_state["_pending_single_key"] = key
                        st.rerun()
                else:
                    st.rerun()

    # Col 3: 总结按钮（核心三项完成后可用）
    with _action_cols[3]:
        _summary_type = "primary" if active_view == "summary" else "secondary"
        if core_all_done:
            _summary_label = "✅ 总结"
        else:
            _summary_label = "📊 总结"
        if st.button(_summary_label, type=_summary_type,
                     use_container_width=True, key="btn_summary",
                     disabled=_is_analyzing or not core_all_done):
            st.session_state["active_view"] = "summary"
            st.rerun()

    # 深度分析按钮：仅在核心三项完成后显示（独立行）
    if core_all_done or deep_all_done:
        if deep_all_done:
            st.button("✅ 舆情+板块+股东 深度分析已完成", disabled=True,
                      use_container_width=True, key="btn_deep")
        else:
            if st.button("🔬 开始深度分析（舆情+板块+股东）", use_container_width=True,
                         key="btn_deep", type="primary",
                         disabled=_is_analyzing):
                if client:
                    _run_deep_analysis(client, cfg_now, selected_model, analyses)
                    st.rerun()

    # ── 执行待处理的分析（在按钮行之后、内容区之前）──────────
    if _pending_core and client and stock_ready:
        st.session_state.pop("_pending_core_analysis", None)
        keys_to_run = [k for k in CORE_KEYS if not analyses.get(k)]
        if keys_to_run:
            label_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面"}
            _run_parallel_with_heartbeat(
                keys_to_run, client, cfg_now, selected_model,
                f"一键分析（{len(keys_to_run)}项）", label_map, analyses,
            )
            st.rerun()

    if _pending_single is not None and client and stock_ready:
        _single_labels = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面",
                          "sentiment": "舆情", "sector": "板块", "holders": "股东"}
        _lbl = _single_labels.get(_pending_single, _pending_single)
        if not analyses.get(_pending_single):
            _run_single_analysis(_pending_single, _lbl, client, cfg_now, selected_model, analyses)
            st.rerun()

    # ── 紧凑状态栏 ──────────────────────────────────────────
    active_view = st.session_state.get("active_view", "overview")
    _name_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面"}

    if stock_ready and any(analyses.get(k) for k in CORE_KEYS):
        _status_parts = []
        for k in CORE_KEYS:
            if analyses.get(k):
                _status_parts.append(f'<span style="color:#16a34a;">✅{_name_map[k]}</span>')
            else:
                _status_parts.append(f'<span style="color:#9ca3af;">⬜{_name_map[k]}</span>')

        _deep_map = {"sentiment": "舆情", "sector": "板块", "holders": "股东"}
        if any(analyses.get(k) for k in DEEP_KEYS):
            for dk in DEEP_KEYS:
                if analyses.get(dk):
                    _status_parts.append(f'<span style="color:#16a34a;">✅{_deep_map[dk]}</span>')

        # 缓存来源标识
        _shared_from = st.session_state.get("_shared_from")
        if _shared_from:
            _status_parts.append(
                f'<span style="color:#f59e0b;">📦 缓存 · {_shared_from}</span>'
            )

        _status_line = " &nbsp;|&nbsp; ".join(_status_parts)
        st.markdown(
            f'<div style="font-size:0.75rem;color:#6b7280;margin:4px 0;">{_status_line}</div>',
            unsafe_allow_html=True,
        )

        # 缓存时显示"重新分析"按钮
        if _shared_from:
            if st.button("🔄 忽略缓存，重新分析", key="btn_redo_fresh",
                         type="primary", use_container_width=True):
                st.session_state.pop("_shared_from", None)
                st.session_state["analyses"] = {}
                st.session_state.pop("moe_results", None)
                st.session_state.pop("similarity_results", None)
                st.session_state.pop("_auto_sim", None)
                st.session_state.pop("_analyses_saved_keys", None)
                if client:
                    _run_core_analysis_all(client, cfg_now, selected_model)
                st.session_state["active_view"] = "overview"
                st.rerun()

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
        elif active_view == "summary":
            _render_summary(analyses)

    # 邮件推送已移至总结视图内


def _run_core_analysis_all(client, cfg_now, selected_model):
    """同步并行执行核心三项分析（用于重新分析按钮），带心跳"""
    analyses = st.session_state.get("analyses", {})
    label_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面"}
    _run_parallel_with_heartbeat(
        list(CORE_KEYS), client, cfg_now, selected_model,
        "重新分析", label_map, analyses,
    )


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

    from ai.client import get_ai_client
    _, _, ai_err = get_ai_client(st.session_state.get("selected_model", ""))
    if ai_err:
        st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}，请在左侧切换其他模型。
</div>""", unsafe_allow_html=True)



def _render_expectation(analyses):
    """expectation 视图"""
    _has_deep_exp = bool(analyses.get("sentiment"))
    if analyses.get("expectation"):
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


def _render_trend(analyses):
    """trend 视图（K线图 + 趋势解读 + K线匹配）"""
    _t_name = st.session_state.get("stock_name", "")
    _t_code = st.session_state.get("stock_code", "")
    _t_df = st.session_state.get("price_df", pd.DataFrame())
    _has_deep_trend = (st.session_state.get("_auto_sim")
                       or st.session_state.get("similarity_results"))

    if analyses.get("trend"):
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
    _has_deep_fund = bool(analyses.get("sector") or analyses.get("holders"))

    if analyses.get("fundamentals"):
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
    # 深度股东追加
    if analyses.get("holders"):
        st.markdown("---")
        st.markdown(f"#### 👥 {_f_name} · 股东/机构动向（深度）")
        with st.container(border=True):
            st.markdown(analyses["holders"])


def _render_summary(analyses):
    """总结视图：价值投机雷达 + 三项核心分析结论提炼"""
    name = st.session_state.get("stock_name", "")
    ts_code = st.session_state.get("stock_code", "")

    st.markdown(f"#### 📊 {name} · 投资总结")

    # ── 价值投机雷达 ──
    render_radar_section()

    st.markdown("---")

    # ── 三项核心结论摘要 ──
    st.markdown(f"#### 📝 核心分析要点")

    _summary_map = [
        ("expectation", "🔍 预期差", "预期差分析"),
        ("trend", "📈 趋势研判", "趋势解读"),
        ("fundamentals", "📋 基本面", "基本面分析"),
    ]

    for key, title, fallback_label in _summary_map:
        text = analyses.get(key, "")
        if not text:
            st.caption(f"{title}：尚未完成")
            continue

        # 提取结论段落：优先找"综合结论""总结""操作建议"等关键段
        conclusion = _extract_conclusion(text)
        with st.expander(title, expanded=True):
            st.markdown(conclusion)

    # ── 邮件推送（小按钮）──
    email_addr = st.session_state.get("email_input", "")
    if email_addr:
        st.markdown("---")
        if st.button("📧 发送报告到邮箱", key="send_email"):
            with st.spinner("正在发送..."):
                from utils.email_sender import send_analysis_email
                ok, msg = send_analysis_email(
                    email_addr,
                    name,
                    to_code6(ts_code),
                    st.session_state.get("stock_info", {}),
                    analyses,
                    st.session_state.get("moe_results", {}),
                    st.session_state.get("selected_model", ""),
                )
                if ok:
                    st.success(f"✅ 已发送至 {email_addr}")
                else:
                    st.error(msg)
