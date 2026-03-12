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
)
from ai.client import get_ai_client, get_token_usage
from analysis.runner import (
    get_jobs, start_analysis, collect_result,
    is_running, is_done, any_running,
)

inject_css()


def main():
    # ── Header ────────────────────────────────────────────────────────────
    st.markdown("""
<div class="app-header">
  <h1>📈 呆瓜方后援会专属投研助手</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
  <p style="font-size: 0.8em;"><span style="color: white; font-weight: bold;">立花道雪</span></p>
</div>
""", unsafe_allow_html=True)

    # ── Token 用量显示（右上角） ──────────────────────────────────────────
    usage = get_token_usage()
    total = usage["total"]
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
        ">🪙 Token: {display}</div>""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
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
    for key in ["expectation", "trend", "fundamentals", "moe"]:
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

    bc1, bc2, bc3, bc4, bc5, bc6, bc7 = st.columns(7)
    with bc1:
        btn_exp = st.button(_label("expectation", "预期差分析", "🔍"),
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
        btn_qa = st.button("💬 自由提问", use_container_width=True)
    with bc6:
        btn_all = st.button("🚀 一键分析", type="primary", use_container_width=True)
    with bc7:
        btn_mystic = st.button("🔮 玄学炒股", use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    # 查询股票逻辑
    # ══════════════════════════════════════════════════════════════════════
    if search_btn and query:
        for k in ["analyses", "moe_results", "stock_fin", "stock_cap",
                   "stock_dragon", "qa_history", "similarity_results",
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
            s.update(label="✅ 数据获取完成！", state="complete")

        if data_errors:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>：{' | '.join(data_errors[:3])}
</div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # 按钮响应
    # ══════════════════════════════════════════════════════════════════════
    stock_ready = bool(st.session_state.get("stock_name"))
    any_btn = btn_exp or btn_trend or btn_fund or btn_moe or btn_qa or btn_all or btn_mystic

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

        # ── 如果有后台任务在运行，定时刷新 ─────────────────────────
        if any_running(st.session_state):
            time.sleep(1.5)
            st.rerun()

    # 未查询股票但点了玄学按钮
    elif btn_mystic or st.session_state.get("active_tab") == "mystic":
        client, cfg_now, ai_err = get_ai_client(selected_model)
        _show_mystic(client, cfg_now, selected_model)


def _show_stock_overview():
    """显示股票概览：指标卡片 + K线图"""
    import pandas as pd
    from ui.charts import render_kline

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

        result, err = call_ai(client, cfg, prompt, system=system, max_tokens=4000)

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
