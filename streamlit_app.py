#!/usr/bin/env python3
"""
📈 呆瓜方后援会专属投研助手 v6.01
Multi-Model + Tushare · 模块化架构
"""

import logging
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志（DEBUG → stderr + 文件按日轮转）
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
try:
    from logging.handlers import TimedRotatingFileHandler
    _log_dir = Path(__file__).parent / "logs"
    _log_dir.mkdir(exist_ok=True)
    _file_handler = TimedRotatingFileHandler(
        _log_dir / "app.log", when="midnight", backupCount=7, encoding="utf-8",
    )
    _file_handler.setLevel(logging.INFO)
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(_file_handler)
except Exception:
    pass  # 文件日志非关键路径，失败不影响主流程

import streamlit as st

# ── Page Config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="呆瓜方后援会专属投研助手 v6.01 🌸",
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
from config import (
    MODEL_CONFIGS, MODEL_NAMES, ADMIN_USERNAME,
    CORE_KEYS, DEEP_KEYS, ALL_ANALYSIS_KEYS,
)
from ui.styles import inject_css
from data.tushare_client import (
    ts_ok, get_ts_error, get_data_source, resolve_stock, to_code6,
    get_basic_info, get_price_df, get_financial, get_valuation_history,
)
from ai.client import get_ai_client, get_token_usage
from analysis.runner import run_analysis_sync
from ui.sidebar import render_sidebar
from ui.tabs import (
    render_analysis_tab, render_compare_tab, render_backtest_tab,
    render_moe_tab, render_mystic_tab, render_qa_tab,
)

inject_css()

logger = logging.getLogger(__name__)


def _show_login():
    """显示登录页面"""
    import re
    st.markdown("""
<div class="app-header">
  <h1>📈 呆瓜方后援会专属投研助手 v6.01</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
</div>
""", unsafe_allow_html=True)

    username = st.text_input(
        "用户名", placeholder="例如：呆瓜方、章鱼哥...",
        key="_login_username", label_visibility="collapsed",
    )
    if st.button("🚀 登录", type="primary", use_container_width=True):
        name = username.strip()
        if not name or len(name) < 1 or len(name) > 10:
            st.warning("用户名长度 1-10 个字符")
            return
        if not re.match(r'^[\w\u4e00-\u9fff]+$', name):
            st.warning("仅支持字母、数字、下划线或中文")
            return
        from utils.user_store import load_user, save_user
        user_data = load_user(name)
        from datetime import datetime
        user_data["last_login"] = datetime.now().isoformat(timespec="seconds")
        save_user(user_data)
        st.session_state["current_user"] = name
        st.session_state["_user_base_tokens"] = user_data["token_usage"]["total"]
        st.query_params["u"] = name
        st.rerun()
    st.caption("无需注册，输入用户名即可使用。数据将按用户名保存。")


def _save_analysis_to_history():
    """保存当前分析到用户历史 + 完整归档（查询新股票前调用）"""
    # Phase 3.3: 不再每次都清 _cached_user_data，仅在切换用户时清
    username = st.session_state.get("current_user", "")
    stock_name = st.session_state.get("stock_name", "")
    stock_code = st.session_state.get("stock_code", "")
    if not username or not stock_name:
        return

    analyses = st.session_state.get("analyses", {})
    done_keys = [k for k in ALL_ANALYSIS_KEYS[:6] if analyses.get(k)]
    if not done_keys:
        return

    try:
        from utils.archive import save_archive
        save_archive(st.session_state)
        # 递增归档版本号，使缓存失效（Phase 1.3）
        st.session_state["_archive_gen"] = st.session_state.get("_archive_gen", 0) + 1
    except Exception as e:
        logger.debug("[_auto_save] 归档失败: %s", e)

    parts = []
    label_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面",
                 "sentiment": "舆情", "sector": "板块", "holders": "股东"}
    for k in done_keys:
        text = analyses[k][:80].replace("\n", " ").strip()
        parts.append(f"{label_map.get(k, k)}: {text}")
    summary = " | ".join(parts)[:300]

    session_tokens = get_token_usage()["total"]

    from utils.user_store import add_history_entry
    add_history_entry(
        username=username,
        stock_code=stock_code,
        stock_name=stock_name,
        model=st.session_state.get("selected_model", ""),
        analyses_done=done_keys,
        token_cost=session_tokens,
        summary=summary,
    )
    # 清除用户数据缓存，使历史列表刷新
    st.session_state.pop("_cached_user_data", None)


def main():
    # ── 登录门（支持刷新保持登录） ────────────────────────────────────
    if "current_user" not in st.session_state:
        _saved_user = st.query_params.get("u", "")
        if _saved_user:
            from utils.user_store import load_user
            user_data = load_user(_saved_user)
            st.session_state["current_user"] = _saved_user
            st.session_state["_user_base_tokens"] = user_data["token_usage"]["total"]
        else:
            _show_login()
            return

    current_user = st.session_state["current_user"]

    # ── 启动时清理过期归档（>30天） ─────────────────────────────────────
    if "_archive_cleaned" not in st.session_state:
        try:
            from utils.archive import cleanup_expired
            _removed = cleanup_expired(30)
            if _removed:
                logger.info("[main] 已清理 %d 个过期归档文件", _removed)
        except Exception as e:
            logger.debug("[main] 归档清理失败: %s", e)
        st.session_state["_archive_cleaned"] = True

    # ── 启动调度器 ─────────────────────────────────────────────────────
    try:
        from utils.backup import start_backup_scheduler
        start_backup_scheduler()
    except Exception as e:
        logger.debug("[main] 备份调度器启动失败: %s", e)

    try:
        from utils.scheduler import start_top10_scheduler
        start_top10_scheduler()
    except Exception as e:
        logger.debug("[main] Top10调度器启动失败: %s", e)

    # ── 上方区域折叠控制 ──────────────────────────────────────────────────
    _upper_collapsed = st.session_state.get("_upper_collapsed", False)

    # ── Header ────────────────────────────────────────────────────────────
    if not _upper_collapsed:
        st.markdown("""
<div class="app-header">
  <h1>📈 呆瓜方后援会专属投研助手 v6.01</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
</div>
""", unsafe_allow_html=True)

    # ── Token 用量显示（右上角，含用户名） ─────────────────────────────
    usage = get_token_usage()
    session_tokens = usage["total"]
    user_base = st.session_state.get("_user_base_tokens", 0)
    total = user_base + session_tokens
    if total > 0:
        if total >= 10000:
            display = f"{total / 10000:.1f}万"
        else:
            display = f"{total:,}"
        st.markdown(
            f'<div class="token-badge">👤 {current_user} &nbsp;|&nbsp; 🪙 {display}</div>',
            unsafe_allow_html=True,
        )

    # ── Sidebar ───────────────────────────────────────────────────────────
    def _on_logout():
        _save_analysis_to_history()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.query_params.clear()
        st.rerun()

    selected_model, email_addr = render_sidebar(current_user, _on_logout)

    # ── 数据源提示 ────────────────────────────────────────────────────────
    if get_ts_error():
        st.markdown("""<div class="status-banner warn">
  ⚠️ <strong>Tushare 不可用</strong>，已自动切换备用数据源（akshare / 东方财富）。部分数据（龙虎榜）可能缺失。
</div>""", unsafe_allow_html=True)

    # ── 折叠时：展开按钮 + 简化状态 ──────────────────────────────────────
    _top10_pick = st.session_state.pop("_top10_pick", None)
    _fast_rerun_global = st.session_state.pop("_fast_rerun", False)

    if _upper_collapsed:
        if _top10_pick:
            st.session_state["query_input"] = _top10_pick
            st.session_state["_upper_collapsed"] = False
            st.rerun()
        query = st.session_state.get("_last_query", "")
        _auto_search = False
        _go_clicked = False
        _sn = st.session_state.get("stock_name", "")
        _sc = st.session_state.get("stock_code", "")
        _expand_label = f"▽ {_sn}（{_sc}）" if _sn else "▽ 展开搜索区域"
        if st.button(_expand_label, key="btn_expand_upper", use_container_width=True):
            if "_last_query" in st.session_state:
                st.session_state["query_input"] = st.session_state["_last_query"]
            st.session_state["_upper_collapsed"] = False
            st.rerun()

    if not _upper_collapsed:
        # ══════════════════════════════════════════════════════════════════════
        # 🏆 今日 Top10 推荐（折叠区）
        # ══════════════════════════════════════════════════════════════════════
        _fast_rerun_ok = False
        if _fast_rerun_global and st.session_state.get("_top10_cache_key"):
            _top10_cached = st.session_state.get(st.session_state["_top10_cache_key"])
            _top10_display_model = st.session_state.get("_top10_display_model", selected_model)
            if _top10_cached is not None:
                _fast_rerun_ok = True
                from top10.cards import show_top10_cards
                from top10.deep_runner import get_deep_status, is_deep_running
        if not _fast_rerun_ok:
            from top10.runner import (
                get_cached_result as top10_get_cached,
                get_cached_summary as top10_get_summary,
                get_cached_meta as top10_get_meta,
                get_all_cached_models as top10_all_models,
            )
            from top10.cards import show_top10_cards
            from top10.deep_runner import get_deep_status, is_deep_running, start_deep_top10_async

            _top10_cached = top10_get_cached(selected_model)
            _top10_display_model = selected_model
            if _top10_cached is None:
                for _m in top10_all_models():
                    _try = top10_get_cached(_m)
                    if _try is not None:
                        _top10_cached = _try
                        _top10_display_model = _m
                        break
            if _top10_cached is not None:
                from top10.runner import _cache_key
                st.session_state["_top10_cache_key"] = _cache_key(_top10_display_model)
                st.session_state["_top10_display_model"] = _top10_display_model

        # 构建 Top10 标题（含触发者信息）
        if _fast_rerun_ok:
            from top10.runner import _meta_key
            _top10_meta = st.session_state.get(_meta_key(_top10_display_model))
        else:
            _top10_meta = top10_get_meta(_top10_display_model) if _top10_cached is not None else None
        _top10_title = "🏆 今日 Top10 推荐"
        if _top10_meta:
            _m_user = _top10_meta.get("user", "")
            _m_tokens = _top10_meta.get("tokens", 0)
            if _m_tokens >= 10000:
                _m_tokens_display = f"{_m_tokens / 10000:.1f}万"
            else:
                _m_tokens_display = f"{_m_tokens:,}"
            if _m_user:
                _top10_title += f"　(分析来自 **{_m_user}**，共消耗 **{_m_tokens_display}** token)"

        with st.expander(_top10_title, expanded=False):
            if _top10_cached is not None:
                if _fast_rerun_ok:
                    from top10.runner import _summary_key
                    _top10_summary = st.session_state.get(_summary_key(_top10_display_model))
                else:
                    _top10_summary = top10_get_summary(_top10_display_model)
                if _top10_summary:
                    st.markdown(_top10_summary)
                    st.markdown("---")
                show_top10_cards(_top10_cached)

                _ds = get_deep_status()
                if _ds and _ds.get("status") == "done" and _ds.get("tokens_used"):
                    _total_tk = _ds["tokens_used"]
                    _scored_n = _ds.get("scored_count", 0)
                    _deep_n = _ds.get("deep_count", 0)
                    _started = _ds.get("started", "")[:16].replace("T", " ")
                    _finished = _ds.get("finished", "")[:16].replace("T", " ")
                    if _total_tk >= 10000:
                        _tk_str = f"{_total_tk / 10000:.1f}万"
                    else:
                        _tk_str = f"{_total_tk:,}"
                    _avg = _total_tk // _deep_n if _deep_n else 0
                    st.markdown(
                        f'<div style="text-align:center;color:#9ca3af;font-size:0.72rem;'
                        f'margin-top:12px;padding:6px;border-top:1px solid #f1f5f9;">'
                        f'🪙 本次分析共消耗 <b>{_tk_str}</b> token '
                        f'（{_scored_n}只评分 + {_deep_n}只深度分析，'
                        f'均值 {_avg:,}/只） · '
                        f'{_started} ~ {_finished}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            elif is_deep_running():
                _deep_status = get_deep_status() or {}
                _phase = _deep_status.get("phase", "初始化")
                st.info(f"🔬 深度 Top10 分析正在后台运行中（当前阶段：**{_phase}**）")
                st.caption("分析完成后刷新页面即可查看结果")
                time.sleep(3)
                st.rerun()
            else:
                _deep_status = get_deep_status()
                if _deep_status and _deep_status.get("status") == "error":
                    st.error(f"上次深度分析失败：{_deep_status.get('error', '未知错误')}")

                st.caption("每晚 22:00 自动运行深度分析（100只候选全量深度分析 + MoE辩论），结果每日刷新。")

                if current_user == ADMIN_USERNAME:
                    st.markdown("---")
                    st.markdown("##### 🔧 管理员操作")
                    _admin_col1, _admin_col2 = st.columns([2, 1])
                    with _admin_col1:
                        _admin_model = st.selectbox(
                            "分析模型", MODEL_NAMES,
                            index=MODEL_NAMES.index("🟤 豆包 · Seed 2.0 Mini")
                            if "🟤 豆包 · Seed 2.0 Mini" in MODEL_NAMES else 0,
                            key="admin_top10_model",
                        )
                    with _admin_col2:
                        _admin_pool = st.number_input(
                            "候选池", min_value=20, max_value=200, value=100,
                            step=10, key="admin_top10_pool",
                        )
                    if st.button("🚀 手动触发深度 Top10 分析", type="primary",
                                 use_container_width=True, key="btn_admin_deep_top10"):
                        ok = start_deep_top10_async(
                            model_name=_admin_model,
                            candidate_count=_admin_pool,
                            username=current_user,
                        )
                        if ok:
                            st.success("✅ 深度分析已在后台启动，预计需要较长时间，请稍后刷新查看")
                        else:
                            st.warning("⏳ 已有分析任务在运行中")
                        st.rerun()

        # ══════════════════════════════════════════════════════════════════════
        # 搜索栏 + 开始分析 + 重置（同一行）
        # ══════════════════════════════════════════════════════════════════════
        if _top10_pick:
            st.session_state["query_input"] = _top10_pick

        _core_all_have = all(
            st.session_state.get("analyses", {}).get(k)
            for k in CORE_KEYS
        ) if st.session_state.get("stock_name") else False

        if _core_all_have:
            _go_label = "✅ 分析完成"
            _go_disabled = True
        else:
            _go_label = "🚀 一键分析"
            _go_disabled = False

        # 构建股票搜索候选列表（带缓存）
        if "_stock_options" not in st.session_state or st.session_state.get("_stock_opts_ver") != 2:
            try:
                from data.tushare_client import load_stock_list
                _sl_df, _ = load_stock_list()
                if not _sl_df.empty:
                    _opts = [
                        f"{str(row.get('symbol', row.get('ts_code', '').split('.')[0])).zfill(6)} {row.get('name', '')}"
                        for _, row in _sl_df.iterrows()
                    ]
                    st.session_state["_stock_options"] = sorted(_opts)
                else:
                    st.session_state["_stock_options"] = []
                st.session_state["_stock_opts_ver"] = 2
            except Exception:
                st.session_state["_stock_options"] = []
                st.session_state["_stock_opts_ver"] = 2

        _stock_options = st.session_state["_stock_options"]

        _search_col, _go_col, _reset_col = st.columns([4, 1.5, 1])
        with _search_col:
            if _stock_options:
                # 如果有预加载候选，提供 selectbox（自带搜索过滤）
                _default_idx = None
                _prev_q = st.session_state.get("query_input", "")
                if _prev_q and _prev_q in _stock_options:
                    _default_idx = _stock_options.index(_prev_q)
                query = st.selectbox(
                    "搜索股票", options=_stock_options,
                    index=_default_idx, label_visibility="collapsed",
                    placeholder="🔍 输入股票代码或名称搜索…",
                    key="query_input",
                )
            else:
                query = st.text_input(
                    "搜索股票", label_visibility="collapsed",
                    placeholder="🔍 股票代码或名称…",
                    key="query_input",
                )
        with _go_col:
            _go_clicked = st.button(_go_label, type="secondary",
                                     use_container_width=True, key="btn_go",
                                     disabled=_go_disabled)
        with _reset_col:
            _reset_clicked = st.button("🔄 重置", type="secondary",
                                        use_container_width=True, key="btn_reset")

        _auto_search = bool(_top10_pick)

        # 重置：清除分析状态，保留登录
        if _reset_clicked:
            _save_analysis_to_history()
            _keep = {"current_user", "_user_base_tokens", "selected_model"}
            for k in list(st.session_state.keys()):
                if k not in _keep:
                    del st.session_state[k]
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # 股票解析 + 最少数据获取
    # ══════════════════════════════════════════════════════════════════════
    def _resolve_and_fetch(q: str):
        """解析股票 + 获取最少通用数据（info/K线/财务/估值），立即返回以启动分析"""
        # selectbox 选中值格式为 "000001 平安银行"，提取6位代码
        q = q.strip()
        if " " in q:
            q = q.split()[0]  # 取代码部分（已 zfill(6)）
        _save_analysis_to_history()
        for k in ["analyses", "moe_results", "stock_fin",
                   "valuation_df",
                   "qa_history", "similarity_results", "_show_sim",
                   "active_tab", "active_view", "_auto_sim", "_jobs",
                   "_analyses_saved_keys", "_last_archive", "_last_archive_file",
                   "_shared_from", "_archive_lookup"]:
            st.session_state.pop(k, None)
        for k in list(st.session_state.keys()):
            if k.startswith("_confirm_redo_"):
                del st.session_state[k]
        st.session_state["analyses"] = {}
        # 清除图表缓存（股票切换了）
        for k in list(st.session_state.keys()):
            if k.startswith("_fig_kline_") or k.startswith("_fig_val_"):
                del st.session_state[k]

        with st.spinner("🔍 解析股票中..."):
            ts_code, name, resolve_warn = resolve_stock(q)
        if resolve_warn:
            st.markdown(f'<div class="status-banner warn">⚠️ {resolve_warn}</div>',
                        unsafe_allow_html=True)

        st.session_state["stock_code"] = ts_code
        st.session_state["stock_name"] = name
        data_errors = []

        with st.spinner(f"📥 正在获取 {name} 的核心数据..."):
            from concurrent.futures import ThreadPoolExecutor, as_completed
            _fetch_map = {
                "info": lambda: get_basic_info(ts_code),
                "price": lambda: get_price_df(ts_code),
                "fin": lambda: get_financial(ts_code),
                "val": lambda: get_valuation_history(ts_code),
            }
            _fetch_results = {}
            with ThreadPoolExecutor(max_workers=4) as _pool:
                _futs = {_pool.submit(fn): key for key, fn in _fetch_map.items()}
                for fut in as_completed(_futs):
                    _fetch_results[_futs[fut]] = fut.result()

            info, e = _fetch_results["info"]
            if e: data_errors.append(e)
            st.session_state["stock_info"] = info

            # 补全股票名称：resolve_stock 未找到名称时会返回代码作为 name
            _cur_name = st.session_state.get("stock_name", "")
            if _cur_name and _cur_name.replace(".", "").isdigit():
                _real_name = info.get("名称", "") or info.get("name", "")
                if _real_name:
                    st.session_state["stock_name"] = _real_name

            df, e = _fetch_results["price"]
            if e: data_errors.append(e)
            st.session_state["price_df"] = df

            fin, e = _fetch_results["fin"]
            if e: data_errors.append(e)
            st.session_state["stock_fin"] = fin

            val_df, e = _fetch_results["val"]
            if e: data_errors.append(e)
            st.session_state["valuation_df"] = val_df

        if data_errors:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>：{' | '.join(data_errors[:3])}
</div>""", unsafe_allow_html=True)

        # 最低数据量校验：至少 20 天交易数据
        if not df.empty and len(df) < 20:
            st.warning(f"⚠️ 仅获取到 {len(df)} 天交易数据（建议至少 20 天），分析结果可能不准确。")

        # ── 智能归档恢复：先加载缓存，已有的 key 不再花 token ──
        from utils.archive import find_recent, load_archive
        _recent = find_recent(ts_code)
        if _recent:
            _recent_data = load_archive(_recent["file"])
            if _recent_data and _recent_data.get("analyses"):
                restored = _recent_data["analyses"]
                st.session_state["analyses"] = restored
                if _recent_data.get("moe_results"):
                    st.session_state["moe_results"] = {
                        **_recent_data["moe_results"], "done": True,
                    }
                _ts_short = _recent.get("ts", "")[11:16]
                _from_user = _recent.get("username", "")
                st.session_state["_shared_from"] = (
                    f"{_from_user} · {_recent.get('model', '')} · {_ts_short}"
                )
                st.session_state["_archive_restored"] = (
                    f"已从归档恢复 {len(restored)} 项分析"
                    f"（{_from_user} · {_recent.get('model', '')} · {_ts_short}）"
                )
                logger.debug("[resolve] 从归档恢复 %d 项分析: %s",
                             len(restored), list(restored.keys()))

    # Top10 自动跳转触发
    if _auto_search and _top10_pick:
        _resolve_and_fetch(_top10_pick)
        st.session_state["_last_query"] = _top10_pick
        st.rerun()

    # ── 处理从 analysis tab 来的待解析请求（Phase 2.1 协作）──
    _pending_resolve = st.session_state.pop("_pending_resolve", None)
    _pending_key = st.session_state.pop("_pending_analysis_key", None)
    if _pending_resolve:
        _resolve_and_fetch(_pending_resolve)
        st.session_state["_last_query"] = _pending_resolve
        client, cfg_now, _ = get_ai_client(selected_model)
        # 分析将在 analysis tab 中按需同步执行
        st.session_state["active_view"] = _pending_key or "overview"
        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # 获取 AI 客户端（各 Tab 共用）
    # ══════════════════════════════════════════════════════════════════════
    stock_ready = bool(st.session_state.get("stock_name"))
    analyses = st.session_state.get("analyses", {})

    # 归档恢复醒目提示
    _archive_msg = st.session_state.pop("_archive_restored", None)
    if _archive_msg:
        st.success(f"✅ {_archive_msg}")
    client, cfg_now, ai_err = get_ai_client(selected_model)

    # 搜索栏"一键分析"按钮触发逻辑
    if _go_clicked:
        if not query:
            st.toast("请先输入股票代码或名称")
        else:
            # selectbox 值格式为 "代码 名称"，提取代码部分
            query = query.split()[0] if query and " " in query else query
            _last_q = st.session_state.get("_last_query", "")
            _need_fetch = not stock_ready or query != _last_q
            if _need_fetch:
                _resolve_and_fetch(query)
                st.session_state["_last_query"] = query
                stock_ready = True
                analyses = st.session_state.get("analyses", {})  # 刷新（可能已从归档恢复）
            # 标记待执行的核心分析，交给 analysis tab 内部执行（保持 Tab/按钮可见）
            if client:
                keys_to_run = [k for k in CORE_KEYS if not analyses.get(k)]
                if keys_to_run:
                    st.session_state["_pending_core_analysis"] = True

            st.session_state["active_view"] = "overview"
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # 未选股时：显示引导，隐藏 Tab 和按钮行
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # Tab 布局 — 始终显示（未选股时各 Tab 内部自行显示引导）
    # ══════════════════════════════════════════════════════════════════════
    tab_analysis, tab_compare, tab_backtest, tab_moe, tab_mystic, tab_qa = st.tabs(
        ["📊 智能分析", "⚖️ 股票对比", "📈 回测战绩", "🎯 六方会谈", "🔮 玄学炒股", "💬 互动问答"]
    )

    with tab_analysis:
        render_analysis_tab(client, cfg_now, selected_model, email_addr)
    with tab_compare:
        render_compare_tab(client, cfg_now, selected_model)
    with tab_backtest:
        render_backtest_tab()
    with tab_moe:
        render_moe_tab(client, cfg_now, selected_model)
    with tab_mystic:
        render_mystic_tab(client, cfg_now, selected_model)
    with tab_qa:
        render_qa_tab(client, cfg_now, selected_model)

    # ══════════════════════════════════════════════════════════════════════
    # 增量归档（同步执行完成后检查）
    # ══════════════════════════════════════════════════════════════════════
    if stock_ready:
        _analyses_saved = st.session_state.get("_analyses_saved_keys", set())
        _analyses_now = set(k for k, v in analyses.items() if v and len(v) > 100)
        if _analyses_now - _analyses_saved:
            try:
                from utils.archive import save_archive
                save_archive(st.session_state)
                st.session_state["_analyses_saved_keys"] = _analyses_now.copy()
                st.session_state["_archive_gen"] = st.session_state.get("_archive_gen", 0) + 1
            except Exception as e:
                logger.debug("[archive] 归档失败: %s", e)


if __name__ == "__main__":
    main()
