#!/usr/bin/env python3
"""
📈 呆瓜方后援会专属投研助手 v5
Multi-Model + Tushare · 模块化架构
"""

import logging
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志（DEBUG 级别输出到 stderr，不影响 Streamlit UI）
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

import streamlit as st

# ── Page Config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="呆瓜方后援会专属投研助手 🌸",
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
from ui.results import (
    _show_analysis_result, _show_job_progress,
    _render_moe_results, _show_similarity_section,
    _render_free_question, render_radar_section,
)
from data.tushare_client import (
    ts_ok, get_ts_error, get_data_source, resolve_stock, to_code6,
    get_basic_info, get_price_df, get_financial, get_valuation_history,
)
from ai.client import get_ai_client, get_token_usage
from analysis.runner import (
    get_jobs, start_analysis, collect_result,
    is_running, is_done, any_running,
)

inject_css()

logger = logging.getLogger(__name__)


def _show_login():
    """显示登录页面"""
    import re
    st.markdown("""
<div class="app-header">
  <h1>📈 呆瓜方后援会专属投研助手</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
  <p style="font-size: 0.8em;"><span style="color: white; font-weight: bold;">立花道雪</span></p>
</div>
""", unsafe_allow_html=True)

    # 不使用 st.columns，避免触发按钮行 nowrap CSS 规则
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
        # 加载/创建用户数据
        from utils.user_store import load_user, save_user
        user_data = load_user(name)
        from datetime import datetime
        user_data["last_login"] = datetime.now().isoformat(timespec="seconds")
        save_user(user_data)
        # 记录累计token基数（登录时加载）
        st.session_state["current_user"] = name
        st.session_state["_user_base_tokens"] = user_data["token_usage"]["total"]
        st.query_params["u"] = name  # 刷新页面后自动恢复登录
        st.rerun()
    st.caption("无需注册，输入用户名即可使用。数据将按用户名保存。")


def _save_analysis_to_history():
    """保存当前分析到用户历史 + 完整归档（查询新股票前调用）"""
    st.session_state.pop("_cached_user_data", None)  # 清除缓存，下次重新加载
    username = st.session_state.get("current_user", "")
    stock_name = st.session_state.get("stock_name", "")
    stock_code = st.session_state.get("stock_code", "")
    if not username or not stock_name:
        return

    analyses = st.session_state.get("analyses", {})
    done_keys = [k for k in ["expectation", "trend", "fundamentals",
                              "sentiment", "sector", "holders"] if analyses.get(k)]
    if not done_keys:
        return

    # 完整归档（含全文，供回测）
    try:
        from utils.archive import save_archive
        save_archive(st.session_state)
    except Exception as e:
        logger.debug("[_auto_save] 归档失败: %s", e)

    # 生成摘要：每个分析取前80字
    parts = []
    label_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面",
                 "sentiment": "舆情", "sector": "板块", "holders": "股东"}
    for k in done_keys:
        text = analyses[k][:80].replace("\n", " ").strip()
        parts.append(f"{label_map.get(k, k)}: {text}")
    summary = " | ".join(parts)[:300]

    # Token消耗估算（本次session增量）
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


def main():
    # ── 登录门（支持刷新保持登录） ────────────────────────────────────
    if "current_user" not in st.session_state:
        # 尝试从 URL 参数恢复登录
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

    # ── 启动每日备份调度器（12:00 GitHub+邮件） ───────────────────────
    try:
        from utils.backup import start_backup_scheduler
        start_backup_scheduler()
    except Exception as e:
        logger.debug("[main] 备份调度器启动失败: %s", e)

    # ── 启动 Top10 定时调度器（22:00 北京时间） ────────────────────────
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
  <h1>📈 呆瓜方后援会专属投研助手</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
  <p style="font-size: 0.8em;"><span style="color: white; font-weight: bold;">立花道雪</span></p>
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
    with st.sidebar:
        st.markdown(f"**👤 {current_user}**")
        if st.button("🔄 切换用户", key="logout_btn"):
            _save_analysis_to_history()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.query_params.clear()  # 清除 URL 参数
            st.rerun()

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
        # 缓存用户数据到 session_state，避免每次 rerun 读文件
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

        # ── 管理后台（仅 LT 可见）────────────────────────────────────
        if current_user == "LT":
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
                    # 展开某用户的详细历史
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
                        # 每日Token明细
                        _daily = _ud.get("token_usage", {}).get("daily", {})
                        if _daily:
                            st.markdown("**每日Token用量：**")
                            for _day in sorted(_daily.keys(), reverse=True)[:7]:
                                _dv = _daily[_day]
                                st.caption(f"{_day} · {_dv.get('total', 0):,} tokens")
                else:
                    st.caption("暂无用户数据")

                # 归档统计 + 手动备份
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

        st.markdown("---")
        st.markdown("""
<div class="disclaimer">
⚠️ <strong>免责声明</strong><br>
本工具仅供学习研究，不构成任何投资建议。A股市场风险较大，请独立判断，自行承担投资盈亏。
</div>
""", unsafe_allow_html=True)

    # ── 数据源提示 ────────────────────────────────────────────────────────
    if get_ts_error():
        st.markdown("""<div class="status-banner warn">
  ⚠️ <strong>Tushare 不可用</strong>，已自动切换备用数据源（akshare / 东方财富）。部分数据（龙虎榜）可能缺失。
</div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # 收集已完成的后台任务结果（每次 rerun 都执行）
    # ══════════════════════════════════════════════════════════════════════
    for key in ["expectation", "trend", "fundamentals", "moe",
                 "sentiment", "sector", "holders"]:
        collect_result(st.session_state, key)

    # ── 折叠时：展开按钮 + 简化状态 ──────────────────────────────────────
    _top10_pick = st.session_state.pop("_top10_pick", None)

    if _upper_collapsed:
        if _top10_pick:
            st.session_state["query_input"] = _top10_pick
            st.session_state["_upper_collapsed"] = False
            st.rerun()
        query = st.session_state.get("_last_query", "")
        _auto_search = False
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
        from top10.runner import (
            get_cached_result as top10_get_cached,
            get_cached_summary as top10_get_summary,
            get_cached_meta as top10_get_meta,
            get_all_cached_models as top10_all_models,
        )
        from top10.cards import show_top10_cards
        from top10.deep_runner import get_deep_status, is_deep_running, start_deep_top10_async

        # 尝试找到今日已有缓存的模型（优先选中模型，否则取第一个有缓存的）
        _top10_cached = top10_get_cached(selected_model)
        _top10_display_model = selected_model
        if _top10_cached is None:
            for _m in top10_all_models():
                _try = top10_get_cached(_m)
                if _try is not None:
                    _top10_cached = _try
                    _top10_display_model = _m
                    break

        # 构建 Top10 标题（含触发者信息）
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
                # 已有今日结果 → 直接展示
                _top10_summary = top10_get_summary(_top10_display_model)
                if _top10_summary:
                    st.markdown(_top10_summary)
                    st.markdown("---")
                show_top10_cards(_top10_cached)

                # Token 消耗小贴士（底部淡色显示）
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
                # 深度分析正在运行
                _deep_status = get_deep_status() or {}
                _phase = _deep_status.get("phase", "初始化")
                st.info(f"🔬 深度 Top10 分析正在后台运行中（当前阶段：**{_phase}**）")
                st.caption("分析完成后刷新页面即可查看结果")
                time.sleep(3)
                st.rerun()
            else:
                # 无缓存
                _deep_status = get_deep_status()
                if _deep_status and _deep_status.get("status") == "error":
                    st.error(f"上次深度分析失败：{_deep_status.get('error', '未知错误')}")

                st.caption("每晚 22:00 自动运行深度分析（100只候选全量深度分析 + MoE辩论），结果每日刷新。")

                # 仅管理员 LT 可手动触发
                if current_user == "LT":
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

        # 根据分析状态决定按钮文案和可点击性
        _any_analysis_running = any_running(st.session_state)
        _core_all_have = all(
            st.session_state.get("analyses", {}).get(k)
            or is_running(st.session_state, k)
            for k in ["expectation", "trend", "fundamentals"]
        ) if st.session_state.get("stock_name") else False

        if _any_analysis_running:
            _go_label = "⏳ 分析中…"
            _go_disabled = True
        elif _core_all_have:
            _go_label = "✅ 分析完成"
            _go_disabled = True
        else:
            _go_label = "🚀 一键分析"
            _go_disabled = False

        _search_col, _go_col, _reset_col = st.columns([3, 2, 1.2])
        with _search_col:
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
    # 股票解析 + 最少数据获取（由一键分析或各分析按钮触发）
    # ══════════════════════════════════════════════════════════════════════
    def _resolve_and_fetch(q: str):
        """解析股票 + 获取最少通用数据（info/K线/财务/估值），立即返回以启动分析"""
        _save_analysis_to_history()
        for k in ["analyses", "moe_results", "stock_fin",
                   "valuation_df",
                   "qa_history", "similarity_results", "_show_sim",
                   "active_tab", "active_view", "_auto_sim", "_jobs"]:
            st.session_state.pop(k, None)
        for k in list(st.session_state.keys()):
            if k.startswith("_confirm_redo_"):
                del st.session_state[k]
        st.session_state["analyses"] = {}

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

    # Top10 自动跳转触发
    if _auto_search and _top10_pick:
        _resolve_and_fetch(_top10_pick)
        st.session_state["_last_query"] = _top10_pick
        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # 获取 AI 客户端（各 Tab 共用）
    # ══════════════════════════════════════════════════════════════════════
    stock_ready = bool(st.session_state.get("stock_name"))
    analyses = st.session_state.get("analyses", {})
    client, cfg_now, ai_err = get_ai_client(selected_model)
    core_keys = ["expectation", "trend", "fundamentals"]

    # 搜索栏"一键分析"按钮触发逻辑（在 Tab 之前处理）
    if _go_clicked:
        if not query:
            st.toast("请先输入股票代码或名称")
        else:
            _last_q = st.session_state.get("_last_query", "")
            _need_fetch = not stock_ready or query != _last_q
            if _need_fetch:
                _resolve_and_fetch(query)
                st.session_state["_last_query"] = query
                stock_ready = True
            if client:
                for key in core_keys:
                    if not analyses.get(key) and not is_running(st.session_state, key):
                        start_analysis(st.session_state, key, client, cfg_now,
                                       selected_model)
            st.session_state["active_view"] = "overview"
            st.session_state["_skip_poll_sleep"] = True
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # 未选股时：显示引导，隐藏 Tab 和按钮行
    # ══════════════════════════════════════════════════════════════════════
    if not stock_ready and not _top10_pick:
        st.markdown(
            '<div style="text-align:center;color:#9ca3af;padding:2.5rem 1rem;font-size:0.88rem;">'
            '👆 在上方输入股票代码或名称，点击「一键分析」即可开始'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ══════════════════════════════════════════════════════════════════════
    # Tab 布局
    # ══════════════════════════════════════════════════════════════════════
    tab_analysis, tab_compare, tab_backtest, tab_moe, tab_mystic, tab_qa = st.tabs(
        ["📊 智能分析", "⚖️ 股票对比", "📈 回测战绩", "🎯 六方会谈", "🔮 玄学炒股", "💬 互动问答"]
    )

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: 📊 智能分析
    # ══════════════════════════════════════════════════════════════════════
    with tab_analysis:
        deep_keys = ["sentiment", "sector", "holders"]

        # ── active_view 初始化 ────────────────────────────────────
        if "active_view" not in st.session_state:
            st.session_state["active_view"] = "overview"
        active_view = st.session_state["active_view"]

        # ── 操作栏：3 按钮（预期差 / 趋势 / 基本面）──
        _action_cols = st.columns(3)

        core_all_done = stock_ready and all(
            analyses.get(k) for k in core_keys
        )
        core_all_started = stock_ready and all(
            (analyses.get(k) or is_running(st.session_state, k)) for k in core_keys
        )
        deep_all_done = all(analyses.get(k) for k in deep_keys)
        deep_any_running = any(is_running(st.session_state, k) for k in deep_keys)

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

                if st.button(_btn_label, type=_btn_type,
                             use_container_width=True, key=f"btn_{key}",
                             disabled=(not stock_ready and not query)):
                    st.session_state["active_view"] = key
                    if not done and not running:
                        if not stock_ready and query:
                            _resolve_and_fetch(query)
                            st.session_state["_last_query"] = query
                            stock_ready = True
                        if client and stock_ready:
                            start_analysis(st.session_state, key, client, cfg_now,
                                           selected_model)
                    st.session_state["_skip_poll_sleep"] = True
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
                        for dk in deep_keys:
                            if not analyses.get(dk) and not is_running(st.session_state, dk):
                                start_analysis(st.session_state, dk, client, cfg_now,
                                               selected_model)
                        st.session_state["_auto_sim"] = True
                    st.session_state["_skip_poll_sleep"] = True
                    st.rerun()

        # ── 紧凑状态栏 ──────────────────────────────────────────
        active_view = st.session_state.get("active_view", "overview")
        _jobs = get_jobs(st.session_state)
        _name_map = {"expectation": "预期差", "trend": "趋势", "fundamentals": "基本面"}

        if stock_ready and (any(analyses.get(k) for k in core_keys)
                           or any(is_running(st.session_state, k) for k in core_keys)):
            _status_parts = []
            for k in core_keys:
                if analyses.get(k):
                    _status_parts.append(f'<span style="color:#16a34a;">✅{_name_map[k]}</span>')
                elif is_running(st.session_state, k):
                    _status_parts.append(
                        f'<span style="color:#6366f1;">'
                        f'⏳{_name_map[k]}分析中<span class="loading-dots"></span></span>'
                    )
                else:
                    _status_parts.append(f'<span style="color:#9ca3af;">⬜{_name_map[k]}</span>')

            # 深度分析状态
            _deep_map = {"sentiment": "舆情", "sector": "板块", "holders": "股东"}
            if deep_any_running or any(analyses.get(k) for k in deep_keys):
                for dk in deep_keys:
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
            # ════════════════════════════════════════════════════════
            # overview 视图（基本指标 + 实时进度 + 雷达）
            # ════════════════════════════════════════════════════════
            if active_view == "overview":
                _show_stock_overview_basic()
                st.markdown("---")

                # 共享缓存检查（仅无分析结果时）
                from utils.shared_cache import find_shared, load_shared
                if not analyses:
                    shared_list = find_shared(
                        st.session_state["stock_code"],
                        exclude_user="",  # 不排除任何人，包括 auto_scheduler
                    )
                    if shared_list:
                        # 自动加载 Top10 深度分析的结果（auto_scheduler）
                        _auto_entry = next(
                            (s for s in shared_list
                             if s["username"] == "auto_scheduler" and s["has_moe"]),
                            None,
                        )
                        if _auto_entry:
                            shared_data = load_shared(_auto_entry["file_path"])
                            if shared_data and shared_data.get("analyses"):
                                st.session_state["analyses"] = shared_data["analyses"]
                                if shared_data.get("moe_results"):
                                    st.session_state["moe_results"] = shared_data["moe_results"]
                                st.session_state["_shared_from"] = (
                                    f"今日Top10深度分析 · {_auto_entry['model_name']}"
                                )
                                st.rerun()

                        # 其他用户的共享缓存（手动加载）
                        _other = [s for s in shared_list
                                  if s["username"] != current_user]
                        if _other:
                            for sh in _other:
                                ts_short = sh["timestamp"][11:16]
                                keys_str = "、".join({
                                    "expectation": "预期差", "trend": "趋势解读",
                                    "fundamentals": "基本面", "sentiment": "舆情",
                                    "sector": "板块", "holders": "股东",
                                }.get(k, k) for k in sh["analyses_keys"])
                                moe_tag = " + MoE辩论" if sh["has_moe"] else ""
                                st.info(
                                    f"📦 **{sh['username']}** 于 {ts_short} 已用 "
                                    f"{sh['model_name']} 分析过此股票（{keys_str}{moe_tag}）"
                                )
                                if st.button(
                                    f"📥 加载 {sh['username']} 的分析结果（免费）",
                                    key=f"load_shared_{sh['username']}_{sh['model_name']}",
                                ):
                                    shared_data = load_shared(sh["file_path"])
                                    if shared_data:
                                        st.session_state["analyses"] = shared_data.get("analyses", {})
                                        if shared_data.get("moe_results"):
                                            st.session_state["moe_results"] = shared_data["moe_results"]
                                        st.session_state["_shared_from"] = (
                                            f"{sh['username']} · {sh['model_name']} · {ts_short}"
                                        )
                                        st.rerun()
                            st.markdown("---")

                # 共享来源标注
                shared_from = st.session_state.get("_shared_from")
                if shared_from and analyses:
                    st.caption(f"📦 当前结果来自共享缓存：{shared_from}（可重新分析覆盖）")

                if ai_err:
                    st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}，请在左侧切换其他模型。
</div>""", unsafe_allow_html=True)

                # 价值投机雷达（核心三项完成后）
                if core_all_done:
                    from ui.results import render_radar_section
                    render_radar_section()

            # ════════════════════════════════════════════════════════
            # expectation 视图（预期差 + 深度舆情）
            # ════════════════════════════════════════════════════════
            elif active_view == "expectation":
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

            # ════════════════════════════════════════════════════════
            # trend 视图（K线图 + 趋势解读 + K线匹配）
            # ════════════════════════════════════════════════════════
            elif active_view == "trend":
                import pandas as pd
                from ui.charts import render_kline
                _t_name = st.session_state.get("stock_name", "")
                _t_code = st.session_state.get("stock_code", "")
                _t_df = st.session_state.get("price_df", pd.DataFrame())
                _has_deep_trend = (st.session_state.get("_auto_sim")
                                   or st.session_state.get("similarity_results"))

                # K线图 + 趋势分析结果
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

                # K线匹配：深度分析触发 _auto_sim 或已有缓存
                if _has_deep_trend:
                    st.markdown("---")
                    _show_similarity_section(
                        st.session_state.get("stock_name", ""),
                        st.session_state.get("stock_code", ""),
                    )

            # ════════════════════════════════════════════════════════
            # fundamentals 视图（估值分位 + 基本面 + 板块 + 股东）
            # ════════════════════════════════════════════════════════
            elif active_view == "fundamentals":
                import pandas as pd
                from ui.charts import render_valuation_bands
                _f_name = st.session_state.get("stock_name", "")
                _f_val_df = st.session_state.get("valuation_df", pd.DataFrame())
                _has_deep_fund = (analyses.get("sector") or analyses.get("holders")
                                  or is_running(st.session_state, "sector")
                                  or is_running(st.session_state, "holders"))

                # 估值分位 + 基本面分析结果
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

            # ── 邮件推送（所有视图共享）──────────────────────────
            if email_addr and analyses and not any_running(st.session_state):
                has_any = any(analyses.get(k) for k in
                             ["expectation", "trend", "fundamentals",
                              "sentiment", "sector", "holders"])
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
                                selected_model,
                            )
                            if ok:
                                st.success(f"✅ 已发送至 {email_addr}")
                            else:
                                st.error(msg)

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: ⚖️ 股票对比
    # ══════════════════════════════════════════════════════════════════════
    with tab_compare:
        _show_compare_tab(client, cfg_now, selected_model)

    # ══════════════════════════════════════════════════════════════════════
    # Tab 3: 📈 回测战绩
    # ══════════════════════════════════════════════════════════════════════
    with tab_backtest:
        _show_backtest_tab()

    # ══════════════════════════════════════════════════════════════════════
    # Tab 4: 🎯 六方会谈（MoE 多角色辩论）
    # ══════════════════════════════════════════════════════════════════════
    with tab_moe:
        _core_keys_moe = ["expectation", "trend", "fundamentals"]
        _core_done_moe = stock_ready and all(analyses.get(k) for k in _core_keys_moe)

        if not stock_ready:
            st.markdown("#### 🎯 六方会谈 · 多角色辩论裁决")
            st.info("请先在「📊 智能分析」中输入股票并完成分析")
            st.caption("六方会谈需要预期差、趋势解读、基本面三项分析结果作为辩论素材")
        elif not _core_done_moe:
            st.markdown("#### 🎯 六方会谈 · 多角色辩论裁决")
            _done_labels = []
            _missing_labels = []
            _lbl = {"expectation": "预期差", "trend": "趋势解读", "fundamentals": "基本面"}
            for k in _core_keys_moe:
                if analyses.get(k):
                    _done_labels.append(f"✅ {_lbl[k]}")
                elif is_running(st.session_state, k):
                    _done_labels.append(f"⏳ {_lbl[k]}分析中…")
                else:
                    _missing_labels.append(_lbl[k])
            _progress_text = " &nbsp;|&nbsp; ".join(_done_labels)
            if _missing_labels:
                _progress_text += f" &nbsp;|&nbsp; ⬜ {'、'.join(_missing_labels)}"
            st.markdown(
                f'<div style="padding:1rem;background:linear-gradient(135deg,#faf5ff,#eff6ff);'
                f'border-radius:10px;border:1px solid #c4b5fd;text-align:center;">'
                f'<div style="font-size:0.95rem;color:#6b7280;margin-bottom:8px;">'
                f'完成核心三项分析后即可启动六方会谈</div>'
                f'<div style="font-size:0.85rem;">{_progress_text}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            # 核心三项已完成 → 可以启动 MoE
            _moe_name = st.session_state.get("stock_name", "")
            st.markdown(f"#### 🎯 {_moe_name} · 六方会谈")

            if is_running(st.session_state, "moe"):
                _show_job_progress("moe", "六方会谈辩论")
            elif moe_done:
                _render_moe_results()
            else:
                st.caption(
                    "六方会谈将召集5位不同角色的专家（价值投机手、技术派、基本面研究员、"
                    "题材猎手、散户代表）对该股进行多角度辩论，最终由首席执行官综合裁决。"
                )
                if st.button("🎯 启动六方会谈", type="primary",
                             use_container_width=True, key="btn_moe_start"):
                    if client and not is_running(st.session_state, "moe"):
                        start_analysis(st.session_state, "moe", client, cfg_now,
                                       selected_model)
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # Tab 5: 🔮 趣味玄学
    # ══════════════════════════════════════════════════════════════════════
    with tab_mystic:
        client_m, cfg_m, _ = get_ai_client(selected_model)
        _show_mystic(client_m, cfg_m, selected_model)

    # ══════════════════════════════════════════════════════════════════════
    # Tab 6: 💬 互动问答
    # ══════════════════════════════════════════════════════════════════════
    with tab_qa:
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

    # ══════════════════════════════════════════════════════════════════════
    # 归档 + 自动刷新
    # ══════════════════════════════════════════════════════════════════════
    if stock_ready:
        _was_running = st.session_state.get("_was_running", False)
        _is_running_now = any_running(st.session_state)
        st.session_state["_was_running"] = _is_running_now

        if _was_running and not _is_running_now:
            try:
                from utils.archive import save_archive
                save_archive(st.session_state)
            except Exception as e:
                logger.debug("[poll] 归档失败: %s", e)
            # 保存到共享缓存
            try:
                from utils.shared_cache import save_shared
                save_shared(
                    stock_code=st.session_state.get("stock_code", ""),
                    stock_name=st.session_state.get("stock_name", ""),
                    model_name=st.session_state.get("selected_model", ""),
                    username=st.session_state.get("current_user", ""),
                    analyses=st.session_state.get("analyses", {}),
                    moe_results=st.session_state.get("moe_results"),
                    stock_info=st.session_state.get("stock_info"),
                )
            except Exception as e:
                logger.debug("[poll] 共享缓存保存失败: %s", e)

        if _is_running_now:
            # 按钮刚触发时跳过 sleep，让 UI 立即刷新
            if st.session_state.pop("_skip_poll_sleep", False):
                st.rerun()
            else:
                time.sleep(0.3)
                st.rerun()


def _show_compare_tab(client, cfg, model_name):
    """⚖️ 股票对比 — 两只股票同屏对比"""
    import pandas as pd
    from analysis.signal import compute_signal

    st.markdown("#### ⚖️ 双股对比分析")
    st.caption("输入两只股票，同屏对比关键指标和 AI 评价，帮你做选择")

    col_a, col_b = st.columns(2)
    with col_a:
        query_a = st.text_input("股票 A", placeholder="代码或名称，如 600519",
                                key="cmp_query_a")
    with col_b:
        query_b = st.text_input("股票 B", placeholder="代码或名称，如 000858",
                                key="cmp_query_b")

    if st.button("⚖️ 开始对比", type="primary", use_container_width=True, key="btn_compare"):
        if not query_a or not query_b:
            st.warning("请输入两只股票")
            return
        with st.spinner("正在获取两只股票数据..."):
            code_a, name_a, err_a = resolve_stock(query_a.strip())
            code_b, name_b, err_b = resolve_stock(query_b.strip())
        if err_a:
            st.warning(f"股票A：{err_a}")
        if err_b:
            st.warning(f"股票B：{err_b}")

        # 获取基本信息
        with st.status("📥 获取对比数据...", expanded=True) as s:
            st.write(f"▶ {name_a} 基本信息...")
            info_a, _ = get_basic_info(code_a)
            st.write(f"▶ {name_b} 基本信息...")
            info_b, _ = get_basic_info(code_b)
            st.write(f"▶ {name_a} K线数据...")
            df_a, _ = get_price_df(code_a, days=60)
            st.write(f"▶ {name_b} K线数据...")
            df_b, _ = get_price_df(code_b, days=60)
            s.update(label="✅ 数据获取完成！", state="complete")

        st.session_state["_cmp_data"] = {
            "name_a": name_a, "code_a": code_a, "info_a": info_a, "df_a": df_a,
            "name_b": name_b, "code_b": code_b, "info_b": info_b, "df_b": df_b,
        }

    # 展示对比结果
    cmp = st.session_state.get("_cmp_data")
    if not cmp:
        return

    name_a, name_b = cmp["name_a"], cmp["name_b"]
    info_a, info_b = cmp["info_a"], cmp["info_b"]

    st.markdown("---")
    st.markdown(f"### {name_a} vs {name_b}")

    # ── 关键指标对比表 ─────────────────────────────────────
    metrics = [
        ("最新价(元)", "最新价"),
        ("市盈率TTM", "PE(TTM)"),
        ("市净率PB", "PB"),
        ("市销率PS", "PS"),
        ("换手率(%)", "换手率%"),
        ("行业", "行业"),
    ]
    rows = []
    for info_key, display_name in metrics:
        va = info_a.get(info_key, "—")
        vb = info_b.get(info_key, "—")
        # 数值比较：标注优劣
        better = ""
        try:
            fa, fb = float(va), float(vb)
            if info_key in ("市盈率TTM", "市净率PB", "市销率PS"):
                # 越低越好（排除负值）
                if 0 < fa < fb:
                    better = "← 优"
                elif 0 < fb < fa:
                    better = "优 →"
            elif info_key == "换手率(%)":
                pass  # 换手率无绝对优劣
        except (ValueError, TypeError):
            pass
        rows.append({
            "指标": display_name,
            name_a: str(va)[:12],
            name_b: str(vb)[:12],
            "": better,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── K线走势对比 ────────────────────────────────────────
    df_a, df_b = cmp.get("df_a", pd.DataFrame()), cmp.get("df_b", pd.DataFrame())
    if not df_a.empty and not df_b.empty:
        import plotly.graph_objects as go
        fig = go.Figure()
        # 归一化收盘价（起点=100）
        if len(df_a) > 0:
            base_a = df_a["close"].iloc[0]
            fig.add_trace(go.Scatter(
                x=df_a["trade_date"], y=df_a["close"] / base_a * 100,
                name=name_a, line=dict(color="#6366f1", width=2),
            ))
        if len(df_b) > 0:
            base_b = df_b["close"].iloc[0]
            fig.add_trace(go.Scatter(
                x=df_b["trade_date"], y=df_b["close"] / base_b * 100,
                name=name_b, line=dict(color="#f59e0b", width=2),
            ))
        fig.update_layout(
            title="近60日走势对比（归一化）",
            yaxis_title="相对涨幅（起点=100）",
            height=350, margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig.update_xaxes(type="category", tickangle=-45, nticks=10)
        st.plotly_chart(fig, use_container_width=True)

    # ── AI 对比点评 ────────────────────────────────────────
    if not client:
        st.caption("AI 模型不可用，无法生成对比点评")
        return

    # 检查缓存
    cmp_key = f"_cmp_ai_{cmp['code_a']}_{cmp['code_b']}"
    cached_comment = st.session_state.get(cmp_key)
    if cached_comment:
        st.markdown("#### 🤖 AI 对比点评")
        st.markdown(cached_comment)
        if st.button("🔄 重新生成点评", key="redo_cmp_ai"):
            st.session_state.pop(cmp_key, None)
            st.rerun()
        return

    if st.button("🤖 生成 AI 对比点评", type="primary", key="btn_cmp_ai"):
        from ai.client import call_ai
        prompt = f"""请对比分析以下两只A股，帮助投资者做选择：

## 股票A：{name_a}（{to_code6(cmp['code_a'])}）
{_format_info_for_ai(info_a)}

## 股票B：{name_b}（{to_code6(cmp['code_b'])}）
{_format_info_for_ai(info_b)}

请从以下维度逐项对比，最后给出明确的选择建议：
1. **估值对比**：PE/PB/PS 谁更便宜，是否合理
2. **成长性**：行业前景、增长潜力
3. **技术面**：近期走势强弱
4. **资金面**：换手率、市场关注度
5. **风险对比**：各自主要风险点

## 最终建议
明确推荐哪只（或各自适合什么策略），给出理由。
"""
        system = "你是专业A股投资顾问，擅长对比分析。请联网搜索两只股票的最新消息辅助判断。回答要具体有数据，不要空泛。"
        with st.spinner("AI 正在对比分析..."):
            result, err = call_ai(client, cfg, prompt, system=system, max_tokens=4000,
                                  username=st.session_state.get("current_user", ""))
        if err:
            st.error(f"对比分析失败：{err}")
        else:
            st.session_state[cmp_key] = result
            st.rerun()


def _show_backtest_tab():
    """📈 回测战绩看板"""
    import pandas as pd
    from utils.backtest import (
        load_all_archives, run_backtest, compute_stats, extract_recommendation,
    )
    from utils.archive import load_archive, get_archive_stats

    st.markdown("#### 📈 AI 荐股回测战绩")
    st.caption("对比历史 AI 分析推荐 vs 实际涨跌，检验 AI 建议的胜率")

    # ── 归档统计概览 ─────────────────────────────────────────
    arch_stats = get_archive_stats()
    if arch_stats["count"] == 0:
        st.info(
            "暂无分析归档数据。使用「📊 智能分析」完成股票分析后，"
            "系统会自动归档，积累数据后即可查看回测战绩。"
        )
        st.caption(
            "💡 提示：回测需要至少 5 个交易日前的分析记录，"
            "才能计算后续涨跌。建议持续使用积累数据。"
        )
        return

    st.markdown(
        f"📦 已归档 **{arch_stats['count']}** 条分析记录 · "
        f"占用 {arch_stats['size_mb']} MB"
    )

    # ── 加载归档列表 ─────────────────────────────────────────
    archives = load_all_archives()
    if not archives:
        st.warning("归档记录加载失败")
        return

    # ── 回测执行 ─────────────────────────────────────────────
    cached_bt = st.session_state.get("_backtest_result")
    if cached_bt is not None:
        bt_df = cached_bt
    else:
        bt_df = pd.DataFrame()

    if st.button("🔄 执行回测（需联网获取后续行情）", type="primary",
                 use_container_width=True, key="btn_backtest"):
        prog = st.progress(0, text="准备回测数据...")
        with st.status("📈 正在执行回测...", expanded=True) as status:
            st.write(f"📦 共 {len(archives)} 条归档记录")

            def _progress(cur, total):
                prog.progress(cur / total,
                              text=f"回测中... {cur}/{total} ({cur*100//total}%)")

            bt_df = run_backtest(progress_callback=_progress)
            prog.progress(1.0, text="✅ 回测完成！")

            if bt_df.empty:
                st.write("⚠️ 无符合条件的回测记录（需至少5个交易日前的分析）")
                status.update(label="⚠️ 暂无可回测数据", state="complete")
            else:
                st.write(f"✅ 回测完成！有效记录 {len(bt_df)} 条")
                status.update(label="✅ 回测完成", state="complete")

        st.session_state["_backtest_result"] = bt_df
        if not bt_df.empty:
            st.rerun()

    if bt_df.empty:
        # 即使没有回测结果，也展示归档记录列表
        st.markdown("---")
        st.markdown("#### 📋 归档记录预览")
        preview_rows = []
        for a in archives[-20:]:
            full = a
            if "analyses" not in a:
                fname = a.get("file", "")
                if fname:
                    full = load_archive(fname) or a

            rec = extract_recommendation(full) if "analyses" in full else {
                "rating": "—", "direction": "unknown"
            }
            preview_rows.append({
                "日期": a.get("date", a.get("archive_date", "")),
                "股票": a.get("stock_name", ""),
                "代码": a.get("stock_code", ""),
                "用户": a.get("username", ""),
                "模型": str(a.get("model", ""))[:10],
                "AI评级": rec["rating"],
                "收盘价": a.get("close", "—"),
            })
        if preview_rows:
            st.dataframe(pd.DataFrame(preview_rows[::-1]),
                         use_container_width=True, hide_index=True)
        return

    # ══════════════════════════════════════════════════════════
    # 回测结果展示
    # ══════════════════════════════════════════════════════════
    stats = compute_stats(bt_df)
    if not stats:
        return

    st.markdown("---")

    # ── 核心指标卡片 ─────────────────────────────────────────
    st.markdown("#### 🏆 核心战绩")
    mc1, mc2, mc3, mc4 = st.columns(4)

    with mc1:
        st.metric("回测记录", f"{stats['total_records']} 条")
    with mc2:
        wr5 = stats.get("win_rate_5d")
        st.metric("5日胜率", f"{wr5}%" if wr5 is not None else "—")
    with mc3:
        wr10 = stats.get("win_rate_10d")
        st.metric("10日胜率", f"{wr10}%" if wr10 is not None else "—")
    with mc4:
        wr20 = stats.get("win_rate_20d")
        st.metric("20日胜率", f"{wr20}%" if wr20 is not None else "—")

    mc5, mc6, mc7, mc8 = st.columns(4)
    with mc5:
        ar5 = stats.get("avg_return_5d")
        st.metric("5日平均收益", f"{ar5:+.2f}%" if ar5 is not None else "—")
    with mc6:
        ar10 = stats.get("avg_return_10d")
        st.metric("10日平均收益", f"{ar10:+.2f}%" if ar10 is not None else "—")
    with mc7:
        ar20 = stats.get("avg_return_20d")
        st.metric("20日平均收益", f"{ar20:+.2f}%" if ar20 is not None else "—")
    with mc8:
        bull_n = stats.get("bullish_count", 0)
        bear_n = stats.get("bearish_count", 0)
        st.metric("看多/看空", f"{bull_n} / {bear_n}")

    # ── 按评级分组收益 ───────────────────────────────────────
    rating_data = stats.get("by_rating", [])
    if rating_data:
        st.markdown("---")
        st.markdown("#### 📊 各评级后续表现")
        rating_df = pd.DataFrame(rating_data)
        # 重命名列
        rename = {"rating": "AI评级", "count": "次数",
                  "avg_5d": "5日平均%", "avg_10d": "10日平均%", "avg_20d": "20日平均%"}
        rating_df = rating_df.rename(columns=rename)
        st.dataframe(rating_df, use_container_width=True, hide_index=True)

    # ── 收益分布图 ───────────────────────────────────────────
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    valid_10d = bt_df[bt_df["return_10d"].notna()]
    if len(valid_10d) > 0:
        st.markdown("---")
        st.markdown("#### 📉 10日收益分布")

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=valid_10d["return_10d"],
            nbinsx=20,
            marker_color=["#22c55e" if x > 0 else "#ef4444"
                          for x in valid_10d["return_10d"]],
            opacity=0.8,
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="#6b7280")
        avg_10 = valid_10d["return_10d"].mean()
        fig.add_vline(x=avg_10, line_dash="dot", line_color="#6366f1",
                      annotation_text=f"均值 {avg_10:.1f}%")
        fig.update_layout(
            xaxis_title="10日涨跌幅 (%)",
            yaxis_title="次数",
            height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            bargap=0.05,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 时间序列：累计收益曲线 ───────────────────────────────
    valid_dated = bt_df[bt_df["return_10d"].notna()].sort_values("date")
    if len(valid_dated) >= 3:
        st.markdown("#### 📈 跟随 AI 建议的累计收益")
        st.caption("假设每次按 AI 建议等仓操作，看多则做多、看空则空仓跳过")

        cumulative = []
        cum_ret = 0
        for _, row in valid_dated.iterrows():
            ret = row["return_10d"]
            if row["direction"] == "bullish":
                cum_ret += ret
            elif row["direction"] == "bearish":
                pass  # 看空时空仓
            else:
                cum_ret += ret * 0.5  # 中性时半仓
            cumulative.append({"date": row["date"], "cumulative": round(cum_ret, 2)})

        cum_df = pd.DataFrame(cumulative)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=cum_df["date"], y=cum_df["cumulative"],
            mode="lines+markers", name="累计收益",
            line=dict(color="#6366f1", width=2),
            fill="tozeroy",
            fillcolor="rgba(99,102,241,0.1)",
        ))
        fig2.add_hline(y=0, line_dash="dash", line_color="#6b7280")
        fig2.update_layout(
            yaxis_title="累计收益 (%)",
            height=300,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── 详细记录表 ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📋 详细回测记录")

    display_df = bt_df[[
        "date", "stock_name", "stock_code", "rating", "direction",
        "close_at_analysis", "return_5d", "return_10d", "return_20d",
        "username", "model",
    ]].copy()
    display_df = display_df.rename(columns={
        "date": "日期", "stock_name": "股票", "stock_code": "代码",
        "rating": "AI评级", "direction": "方向",
        "close_at_analysis": "分析时价格",
        "return_5d": "5日涨跌%", "return_10d": "10日涨跌%",
        "return_20d": "20日涨跌%",
        "username": "分析人", "model": "模型",
    })
    # 方向翻译
    dir_map = {"bullish": "🟢 看多", "bearish": "🔴 看空",
               "neutral": "🟡 中性", "unknown": "❓"}
    display_df["方向"] = display_df["方向"].map(dir_map)
    display_df["模型"] = display_df["模型"].apply(lambda x: str(x)[:12])
    display_df = display_df.sort_values("日期", ascending=False)

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.caption("⚠️ 回测结果仅供参考，历史表现不代表未来收益。AI 分析存在局限性，请独立判断。")


def _format_info_for_ai(info: dict) -> str:
    """格式化股票信息供 AI 对比使用"""
    parts = []
    for key in ["最新价(元)", "市盈率TTM", "市净率PB", "市销率PS",
                "换手率(%)", "行业", "总市值(亿)"]:
        v = info.get(key, "")
        if v and str(v) != "N/A":
            parts.append(f"- {key}: {v}")
    return "\n".join(parts) if parts else "- 数据暂无"


def _show_stock_overview_basic():
    """显示股票概览：仅指标卡片（K线图移至趋势视图，估值分位移至基本面视图）"""
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


def _show_mystic(client, cfg, model_name):
    """🔮 玄学炒股 — 趣味黄历运势"""
    from datetime import datetime
    from ai.client import call_ai

    st.markdown("---")
    st.markdown("#### 🔮 玄学炒股 · 今日运势")

    today_str = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][datetime.now().weekday()]

    # 检查是否已有今日结果缓存
    cached = st.session_state.get("_mystic_result", {})
    if cached.get("date") == today_str:
        st.markdown(cached["content"])
        return

    if not client:
        st.warning("请先在左侧配置 AI 模型")
        return

    with st.status("🔮 正卦象推演中...", expanded=True) as status:
        st.write("📅 获取今日日期与天干地支...")
        time.sleep(0.3)
        st.write("🌙 查询黄历宜忌...")
        time.sleep(0.25)
        st.write("🎴 抽取今日塔罗牌...")
        time.sleep(0.25)
        st.write("🐉 推算生肖与五行运势...")
        time.sleep(0.2)
        st.write("🔮 综合推演炒股运势，请虔诚等待...")

        stock_name = st.session_state.get("stock_name", "")
        stock_extra = f"\n\n用户当前关注的股票：{stock_name}，请也对这只股票给出玄学点评。" if stock_name else ""

        prompt = f"""今天是 {today_str} {weekday}。

请你扮演一位精通易经八卦、紫微斗数、塔罗牌、黄历、星座的玄学大师，为今日的A股炒股运势做一次趣味占卜。

请联网搜索今天的真实黄历信息（天干地支、宜忌、冲煞等），然后结合以下维度给出有趣的分析：

## 要求输出格式（用 emoji 让内容生动有趣）：

### 📅 今日黄历
- 农历日期、天干地支、值神
- 宜：xxx  忌：xxx

### 🎯 今日炒股运势评级
给出一个明确的等级：大吉 / 吉 / 小吉 / 中平 / 小凶 / 凶 / 大凶
并配上一句有趣的点评（模仿古人口吻）

### 🐉 五行与板块
根据今日五行旺衰，推荐适合的板块（如：火旺利军工光伏、水旺利航运水利等）
也指出今日五行克制、应回避的板块

### 🎴 塔罗牌指引
随机抽一张塔罗牌，解读其对今日炒股的启示

### ⏰ 吉时与凶时
给出今日适合买入/卖出的吉时（用十二时辰+现代时间对照）
给出应该避开操作的凶时

### 🎲 今日幸运数字 & 尾号
给出今日幸运数字，以及适合关注的股票代码尾号

### ⚠️ 玄学大师忠告
用一段文言文风格的话总结今日建议，最后加一句现代吐槽（制造反差萌）
{stock_extra}

**注意：这是趣味内容，请在最后用小字提醒用户"以上内容纯属娱乐，不构成投资建议，请理性投资"。**"""

        system = (
            "你是一位学贯中西的玄学大师，精通易经、紫微斗数、塔罗牌、西方星座，"
            "同时对A股市场有深入了解。你的风格：专业中带着幽默，神秘中带着接地气，"
            "古典与现代混搭。请联网搜索今天的真实黄历数据来增强可信度。"
        )

        result, err = call_ai(client, cfg, prompt, system=system, max_tokens=4000,
                              username=st.session_state.get("current_user", ""))

        if err:
            status.update(label="❌ 卦象推演失败", state="error")
            st.error(f"玄学大师暂时失联：{err}")
            return

        st.write("✨ 卦象已成！")
        time.sleep(0.3)
        status.update(label="🔮 今日运势已揭晓！", state="complete")

    # 缓存今日结果
    st.session_state["_mystic_result"] = {"date": today_str, "content": result}
    st.markdown(result)


if __name__ == "__main__":
    main()
