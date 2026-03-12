"""分析执行与结果展示 — 分离执行逻辑和展示逻辑"""

import streamlit as st
import pandas as pd
from ui.charts import render_kline, render_similar_case
from analysis.moe import run_moe, MOE_ROLES
from ai.client import call_ai, call_ai_stream
from ai.context import build_analysis_context
from ai.prompts import (
    build_expectation_prompt,
    build_trend_prompt,
    build_fundamentals_prompt,
)
from data.tushare_client import price_summary
from data.similarity import load_history, find_similar


# ══════════════════════════════════════════════════════════════════════════════
# 流式输出工具
# ══════════════════════════════════════════════════════════════════════════════

def _stream_with_fallback(client, cfg, prompt, system, max_tokens, label):
    """流式输出，返回空则回退非流式"""
    text = st.write_stream(
        call_ai_stream(client, cfg, prompt, system=system, max_tokens=max_tokens)
    )
    if text and text.strip():
        return text
    st.caption(f"⏳ {label} 流式未返回内容，正在重试...")
    fallback_text, err = call_ai(
        client, cfg, prompt, system=system, max_tokens=max_tokens,
    )
    if err:
        st.markdown(
            f'<div class="status-banner warn">⚠️ {label}失败：{err}</div>',
            unsafe_allow_html=True,
        )
        return f"⚠️ {label}失败：{err}"
    if fallback_text:
        st.markdown(fallback_text)
    return fallback_text or ""


# ══════════════════════════════════════════════════════════════════════════════
# 分析执行（根据 actions 字典决定跑哪些模块）
# ══════════════════════════════════════════════════════════════════════════════

def run_analysis(client, cfg, model_name: str, actions: dict):
    """
    执行分析模块
    actions: {"expectation": bool, "trend": bool, "fundamentals": bool,
              "moe": bool, "qa": bool}
    """
    analyses = st.session_state.get("analyses", {})
    name     = st.session_state.get("stock_name", "")
    tscode   = st.session_state.get("stock_code", "")
    df       = st.session_state.get("price_df", pd.DataFrame())
    info     = st.session_state.get("stock_info", {})
    has_client = client is not None

    # ── 预期差分析 ────────────────────────────────────────────────────────
    if actions.get("expectation") and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 🔍 预期差分析中（联网搜索最新资讯）...
</div>""", unsafe_allow_html=True)
        p, s = build_expectation_prompt(name, tscode, info)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "预期差分析")
        analyses["expectation"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 预期差分析完成！")

    # ── 趋势分析 ──────────────────────────────────────────────────────────
    if actions.get("trend") and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 📈 趋势研判中...
</div>""", unsafe_allow_html=True)
        psmry  = price_summary(df)
        cap    = st.session_state.get("stock_cap", "")
        dragon = st.session_state.get("stock_dragon", "")
        p, s = build_trend_prompt(name, tscode, psmry, cap, dragon)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "趋势研判")
        analyses["trend"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 趋势研判完成！")

    # ── 基本面分析 ────────────────────────────────────────────────────────
    if actions.get("fundamentals") and has_client:
        st.markdown("---")
        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 📋 基本面剖析中...
</div>""", unsafe_allow_html=True)
        fin = st.session_state.get("stock_fin", "")
        p, s = build_fundamentals_prompt(name, tscode, info, fin)
        result = _stream_with_fallback(client, cfg, p, s, 8000, "基本面剖析")
        analyses["fundamentals"] = result
        st.session_state["analyses"] = analyses
        st.success("✅ 基本面剖析完成！")

    # ── MoE 辩论裁决 ──────────────────────────────────────────────────────
    if actions.get("moe") and has_client:
        exp_done   = bool(analyses.get("expectation"))
        trend_done = bool(analyses.get("trend"))
        fund_done  = bool(analyses.get("fundamentals"))
        missing = []
        if not exp_done:   missing.append("🔍 预期差分析")
        if not trend_done: missing.append("📈 趋势分析")
        if not fund_done:  missing.append("📋 基本面分析")

        if missing:
            st.markdown("---")
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>MoE 辩论需要前三项分析结果</strong><br>
  请先完成：{'、'.join(missing)}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown("---")
            st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 🎯 MoE 四方辩论裁决中...
</div>""", unsafe_allow_html=True)
            run_moe(client, cfg, name, tscode, analyses)

    # ── 自由提问 ──────────────────────────────────────────────────────────
    if actions.get("qa") and has_client:
        _render_free_question(client, cfg, model_name, name, tscode, info, analyses)


# ══════════════════════════════════════════════════════════════════════════════
# 自由提问
# ══════════════════════════════════════════════════════════════════════════════

def _render_free_question(client, cfg, model_name, name, tscode, info, analyses):
    st.markdown("---")
    st.markdown(f"#### 💬 自由提问 · {name}")

    done_modules = []
    if analyses.get("expectation"):  done_modules.append("预期差")
    if analyses.get("trend"):        done_modules.append("趋势")
    if analyses.get("fundamentals"): done_modules.append("基本面")
    if st.session_state.get("moe_results", {}).get("done"):
        done_modules.append("MoE辩论")

    if done_modules:
        st.caption(f"📎 已有分析上下文：{' · '.join(done_modules)}（将作为参考背景）")
    else:
        st.caption("📎 尚无已完成的分析，AI 将基于股票基本信息和联网搜索回答")

    question = st.text_area(
        "输入你的问题",
        placeholder=f"例如：{name}近期和华为的合作还有炒作预期吗？\n"
                    f"例如：这只股票适合长期持有吗？",
        height=100, key="free_question_input", label_visibility="collapsed",
    )

    if st.button("🚀 提交问题", type="primary", key="submit_free_question"):
        if not question or not question.strip():
            st.warning("请输入你的问题")
            return

        st.markdown(f"""<div class="status-banner info">
  🤖 <strong>{model_name}</strong> · 💬 正在回答...
</div>""", unsafe_allow_html=True)

        context = build_analysis_context(analyses, max_per_module=12)
        metrics_parts = []
        for k in ["最新价(元)", "市盈率TTM", "市净率PB", "行业"]:
            v = info.get(k, "")
            if v and str(v) != "N/A":
                metrics_parts.append(f"{k}={v}")
        metrics_line = " | ".join(metrics_parts) if metrics_parts else "暂无"

        system = (
            f"你是一位专业的A股投资顾问，正在为用户分析 {name}（{tscode}）。"
            f"\n回答原则：以用户问题为核心，引用已有分析结论，联网搜索最新信息，"
            f"回答要具体有数据支撑，涉及操作建议时附带风险提示。"
        )
        prompt = f"""## 股票：{name}（{tscode}）
## 关键指标：{metrics_line}

## 已有分析上下文（仅供参考，以用户问题为主）
{context}

---
## 🎯 用户问题（请重点回答）
{question}

请用中文详细回答。如果问题涉及最新信息，请通过联网搜索获取。"""

        result = _stream_with_fallback(client, cfg, prompt, system, 8000, "自由提问")
        qa_history = st.session_state.get("qa_history", [])
        qa_history.append({"question": question, "answer": result})
        st.session_state["qa_history"] = qa_history


# ══════════════════════════════════════════════════════════════════════════════
# 结果展示（K线 + 相似走势 + 分析结果 Tab 页）
# ══════════════════════════════════════════════════════════════════════════════

def show_completed_results():
    """展示 K 线图 + 已完成的分析结果"""
    name   = st.session_state.get("stock_name", "")
    tscode = st.session_state.get("stock_code", "")
    df     = st.session_state.get("price_df", pd.DataFrame())
    analyses = st.session_state.get("analyses", {})

    if not name:
        return

    # ── K线图 ─────────────────────────────────────────────────────────────
    st.markdown("---")
    render_kline(df, name, tscode)

    # ── 历史相似走势 ──────────────────────────────────────────────────────
    _render_similarity_section(df, tscode, name)

    # ── 分析结果 Tab 页 ──────────────────────────────────────────────────
    has_any = (
        analyses.get("expectation") or analyses.get("trend")
        or analyses.get("fundamentals")
        or st.session_state.get("moe_results", {}).get("done")
        or st.session_state.get("qa_history")
    )
    if not has_any:
        return

    st.markdown("---")
    st.markdown("#### 📊 分析结果")

    tabs, tab_keys = [], []
    if analyses.get("expectation"):
        tabs.append("🔍 预期差"); tab_keys.append("expectation")
    if analyses.get("trend"):
        tabs.append("📈 趋势"); tab_keys.append("trend")
    if analyses.get("fundamentals"):
        tabs.append("📋 基本面"); tab_keys.append("fundamentals")
    if st.session_state.get("moe_results", {}).get("done"):
        tabs.append("🎯 MoE辩论"); tab_keys.append("moe")
    if st.session_state.get("qa_history"):
        tabs.append("💬 提问记录"); tab_keys.append("qa")

    if not tabs:
        return

    tab_objs = st.tabs(tabs)
    for tab_obj, key in zip(tab_objs, tab_keys):
        with tab_obj:
            if key == "moe":
                _render_moe_results()
            elif key == "qa":
                _render_qa_history()
            else:
                content = analyses.get(key, "")
                if content:
                    with st.container(border=True):
                        st.markdown(content)


def _render_moe_results():
    moe = st.session_state.get("moe_results", {})
    if not moe.get("done"):
        return
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


def _render_qa_history():
    qa_history = st.session_state.get("qa_history", [])
    for i, item in enumerate(reversed(qa_history), 1):
        st.markdown(f"**🙋 问题 {len(qa_history) - i + 1}：** {item['question']}")
        with st.container(border=True):
            st.markdown(item["answer"])
        if i < len(qa_history):
            st.markdown("")


# ══════════════════════════════════════════════════════════════════════════════
# 历史相似走势
# ══════════════════════════════════════════════════════════════════════════════

def _render_similarity_section(df, tscode, name):
    history = load_history()
    has_history = not history.empty

    with st.expander("🔎 历史相似走势匹配（全市场搜索，不消耗 Token）", expanded=False):
        if not has_history:
            st.warning(
                "⚠️ 尚未构建历史数据库。请先运行离线脚本：\n\n"
                "```bash\nexport TUSHARE_TOKEN='你的token'\n"
                "python data/build_history.py\n```\n\n"
                "构建完成后将 `data/history/all_daily.parquet` 放入项目目录即可。"
            )
            return
        if df.empty:
            st.info("需要先查询股票获取 K 线数据")
            return

        stock_count = history["ts_code"].nunique()
        date_range = f"{history['trade_date'].min()} ~ {history['trade_date'].max()}"
        st.caption(f"📊 历史数据库：{stock_count} 只股票 · {date_range}")

        col_k, col_btn = st.columns([1, 1])
        with col_k:
            k_days = st.selectbox("匹配窗口天数", options=[3, 5, 10, 20],
                                  index=1, key="sim_k_days")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            run_sim = st.button("🚀 搜索相似走势", type="primary",
                                use_container_width=True, key="run_similarity")

        if run_sim:
            if len(df) < k_days:
                st.warning(f"K线数据不足 {k_days} 天")
                return
            with st.spinner(f"🔍 在 {stock_count} 只股票中搜索..."):
                results = find_similar(target_df=df, k_days=k_days, top_n=3,
                                       context_days=10, exclude_code=tscode)
            if not results:
                st.info("未找到足够相似的历史走势（阈值 > 30%）")
                return
            st.session_state["similarity_results"] = results
            st.success(f"✅ 找到 {len(results)} 个相似走势案例！")

        saved = st.session_state.get("similarity_results", [])
        if saved:
            st.markdown("---")
            for i, case in enumerate(saved, 1):
                render_similar_case(case, i)
                if i < len(saved):
                    st.markdown("")
