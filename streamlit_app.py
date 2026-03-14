#!/usr/bin/env python3
"""
📈 呆瓜方后援会专属投研助手 v5
Multi-Model + Tushare · 模块化架构
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

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
from ui.results import show_completed_results
from data.tushare_client import (
    ts_ok, get_ts_error, get_data_source, resolve_stock, to_code6,
    get_basic_info, get_price_df, get_financial,
    get_capital_flow, get_dragon_tiger,
    get_valuation_history, get_northbound_flow, get_margin_trading,
    get_sector_peers, get_holders_info, get_pledge_info, get_fund_holdings,
)
from ai.client import get_ai_client, get_token_usage
from analysis.runner import (
    get_jobs, start_analysis, collect_result,
    is_running, is_done, any_running,
)

inject_css()


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

    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        st.markdown("#### 👤 请输入用户名登录")
        username = st.text_input(
            "用户名", placeholder="例如：alice、张三",
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
            st.rerun()
        st.caption("无需注册，输入用户名即可使用。数据将按用户名保存。")


def _save_analysis_to_history():
    """保存当前分析到用户历史（查询新股票前调用）"""
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
    # ── 登录门 ─────────────────────────────────────────────────────────
    if "current_user" not in st.session_state:
        _show_login()
        return

    current_user = st.session_state["current_user"]

    # ── Header ────────────────────────────────────────────────────────────
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
        st.markdown(f"""<div style="
            position: fixed; top: 12px; right: 20px; z-index: 9999;
            background: rgba(99, 102, 241, 0.9); color: white;
            padding: 4px 14px; border-radius: 20px;
            font-size: 0.78em; font-weight: 600;
            backdrop-filter: blur(8px); box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        ">👤 {current_user} &nbsp;|&nbsp; 🪙 {display}</div>""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**👤 {current_user}**")
        if st.button("🔄 切换用户", key="logout_btn"):
            _save_analysis_to_history()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

        st.markdown("---")
        st.markdown("### 🤖 选择分析模型")
        selected_model = st.selectbox(
            "当前模型", options=MODEL_NAMES, index=2,
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
        from utils.user_store import load_user
        _udata = load_user(current_user)
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

    # ══════════════════════════════════════════════════════════════════════
    # 搜索栏 + 查询按钮
    # ══════════════════════════════════════════════════════════════════════
    query = st.text_input(
        "搜索股票", label_visibility="collapsed",
        placeholder="🔍  输入股票代码（如 000858）或名称（如 五粮液）…",
        key="query_input",
    )
    search_btn = st.button("🔍 查询股票", type="primary", use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    # 功能按钮（根据后台任务状态显示标签）
    # ══════════════════════════════════════════════════════════════════════
    analyses = st.session_state.get("analyses", {})
    moe_done = bool(st.session_state.get("moe_results", {}).get("done"))

    def _label(key, name, icon):
        if is_running(st.session_state, key):
            return f"⏳ {name}中..."
        done = moe_done if key == "moe" else bool(analyses.get(key))
        if done:
            return f"✅ {name}完成"
        return f"{icon} {name}"

    # 主操作行：一键分析（突出）+ 自由提问
    pr1, pr2, pr3 = st.columns([2, 1, 1])
    with pr1:
        btn_all = st.button("🚀 一键全面分析", type="primary", use_container_width=True)
    with pr2:
        btn_qa = st.button("💬 自由提问", use_container_width=True)
    with pr3:
        btn_mystic = st.button("🔮 玄学炒股", use_container_width=True)

    # 单项分析行（核心三项 + MoE + K线匹配）
    bc1, bc2, bc3, bc4, bc5 = st.columns(5)
    with bc1:
        btn_exp = st.button(_label("expectation", "预期差", "🔍"),
                            use_container_width=True)
    with bc2:
        btn_trend = st.button(_label("trend", "K线趋势", "📈"),
                              use_container_width=True)
    with bc3:
        btn_fund = st.button(_label("fundamentals", "基本面", "📋"),
                             use_container_width=True)
    with bc4:
        btn_moe = st.button(_label("moe", "MoE辩论", "🎯"),
                            use_container_width=True)
    with bc5:
        btn_sim = st.button("📐 K线匹配", use_container_width=True)

    # 深度分析行（舆情 + 板块 + 股东）
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        btn_sentiment = st.button(_label("sentiment", "舆情分析", "📣"),
                                  use_container_width=True)
    with dc2:
        btn_sector = st.button(_label("sector", "板块联动", "🏭"),
                               use_container_width=True)
    with dc3:
        btn_holders = st.button(_label("holders", "股东动向", "👥"),
                                use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    # 查询股票逻辑
    # ══════════════════════════════════════════════════════════════════════
    if search_btn and query:
        # 保存上一轮分析到历史
        _save_analysis_to_history()

        for k in ["analyses", "moe_results", "stock_fin", "stock_cap",
                   "stock_dragon", "stock_northbound", "stock_margin",
                   "valuation_df", "stock_sector_peers", "stock_holders",
                   "stock_pledge", "stock_fund_holdings",
                   "qa_history", "similarity_results",
                   "active_tab", "_jobs"]:
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

            st.write("▶ 历史估值数据（PE/PB分位）...")
            val_df, e = get_valuation_history(ts_code)
            if e: data_errors.append(e)
            st.session_state["valuation_df"] = val_df

            st.write("▶ 北向资金持仓...")
            nb_flow, e = get_northbound_flow(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_northbound"] = nb_flow

            st.write("▶ 融资融券数据...")
            margin, e = get_margin_trading(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_margin"] = margin

            st.write("▶ 同行业个股对比...")
            sector_peers, e = get_sector_peers(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_sector_peers"] = sector_peers

            st.write("▶ 十大股东...")
            holders, e = get_holders_info(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_holders"] = holders

            st.write("▶ 股权质押...")
            pledge, e = get_pledge_info(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_pledge"] = pledge

            st.write("▶ 基金持仓...")
            fund_hold, e = get_fund_holdings(ts_code)
            if e: data_errors.append(e)
            st.session_state["stock_fund_holdings"] = fund_hold
            s.update(label="✅ 数据获取完成！", state="complete")

        if data_errors:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>：{' | '.join(data_errors[:3])}
</div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # 按钮响应
    # ══════════════════════════════════════════════════════════════════════
    stock_ready = bool(st.session_state.get("stock_name"))
    any_btn = (btn_exp or btn_trend or btn_fund or btn_moe or btn_qa or btn_all
               or btn_sim or btn_mystic or btn_sentiment or btn_sector or btn_holders)

    # 玄学炒股不需要先查询股票，单独处理
    if btn_mystic:
        st.session_state["active_tab"] = "mystic"

    if any_btn and not btn_mystic and not stock_ready:
        st.markdown("""<div class="status-banner warn">
  ⚠️ <strong>请先点击「🔍 查询股票」获取数据</strong>，然后再进行分析。
</div>""", unsafe_allow_html=True)
        return

    if stock_ready:
        # 获取 AI 客户端
        client, cfg_now, ai_err = get_ai_client(selected_model)

        # 处理按钮点击：设置 active_tab + 启动后台任务
        if btn_exp:
            st.session_state["active_tab"] = "expectation"
            if client and not analyses.get("expectation") and not is_running(st.session_state, "expectation"):
                start_analysis(st.session_state, "expectation", client, cfg_now, selected_model)
                st.rerun()
        elif btn_trend:
            st.session_state["active_tab"] = "trend"
            if client and not analyses.get("trend") and not is_running(st.session_state, "trend"):
                start_analysis(st.session_state, "trend", client, cfg_now, selected_model)
                st.rerun()
        elif btn_fund:
            st.session_state["active_tab"] = "fundamentals"
            if client and not analyses.get("fundamentals") and not is_running(st.session_state, "fundamentals"):
                start_analysis(st.session_state, "fundamentals", client, cfg_now, selected_model)
                st.rerun()
        elif btn_moe:
            st.session_state["active_tab"] = "moe"
            if client and not moe_done and not is_running(st.session_state, "moe"):
                # MoE 需要前三项
                missing = []
                if not analyses.get("expectation"): missing.append("预期差")
                if not analyses.get("trend"):       missing.append("趋势")
                if not analyses.get("fundamentals"): missing.append("基本面")
                if not missing:
                    start_analysis(st.session_state, "moe", client, cfg_now, selected_model)
                    st.rerun()
        elif btn_sentiment:
            st.session_state["active_tab"] = "sentiment"
            if client and not analyses.get("sentiment") and not is_running(st.session_state, "sentiment"):
                start_analysis(st.session_state, "sentiment", client, cfg_now, selected_model)
                st.rerun()
        elif btn_sector:
            st.session_state["active_tab"] = "sector"
            if client and not analyses.get("sector") and not is_running(st.session_state, "sector"):
                start_analysis(st.session_state, "sector", client, cfg_now, selected_model)
                st.rerun()
        elif btn_holders:
            st.session_state["active_tab"] = "holders"
            if client and not analyses.get("holders") and not is_running(st.session_state, "holders"):
                start_analysis(st.session_state, "holders", client, cfg_now, selected_model)
                st.rerun()
        elif btn_sim:
            st.session_state["active_tab"] = "similarity"
        elif btn_qa:
            st.session_state["active_tab"] = "qa"
        elif btn_all:
            st.session_state["active_tab"] = "all"
            if client:
                for key in ["expectation", "trend", "fundamentals"]:
                    if not analyses.get(key) and not is_running(st.session_state, key):
                        start_analysis(st.session_state, key, client, cfg_now, selected_model)
                st.rerun()

        if ai_err and any_btn:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}<br>
  请在左侧切换其他模型。
</div>""", unsafe_allow_html=True)

        # ── 展示内容 ─────────────────────────────────────────────────
        active_tab = st.session_state.get("active_tab", "")

        if active_tab == "mystic":
            _show_mystic(client, cfg_now, selected_model)
        elif not active_tab:
            _show_stock_overview()
        else:
            show_completed_results(client, cfg_now, selected_model)

        # ── 邮件推送按钮（有分析结果时显示）──────────────────────────
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

        # ── 如果有后台任务在运行，定时刷新 ─────────────────────────
        if any_running(st.session_state):
            time.sleep(1.5)
            st.rerun()

    # 未查询股票但点了玄学按钮
    elif btn_mystic or st.session_state.get("active_tab") == "mystic":
        client, cfg_now, ai_err = get_ai_client(selected_model)
        _show_mystic(client, cfg_now, selected_model)


def _show_stock_overview():
    """显示股票概览：指标卡片 + K线图 + 估值分位图"""
    import pandas as pd
    from ui.charts import render_kline, render_valuation_bands

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

    df = st.session_state.get("price_df", pd.DataFrame())
    if not df.empty:
        st.markdown("---")
        render_kline(df, name, ts_code)

    # 估值历史分位图
    val_df = st.session_state.get("valuation_df", pd.DataFrame())
    if not val_df.empty:
        st.markdown(f"#### 📊 {name} · 估值历史分位")
        render_valuation_bands(val_df, name)


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
        time.sleep(0.6)
        st.write("🌙 查询黄历宜忌...")
        time.sleep(0.5)
        st.write("🎴 抽取今日塔罗牌...")
        time.sleep(0.5)
        st.write("🐉 推算生肖与五行运势...")
        time.sleep(0.4)
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
