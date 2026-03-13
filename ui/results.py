"""分析结果展示 — 读取后台任务进度和结果"""

import time
import streamlit as st
import pandas as pd
from analysis.moe import MOE_ROLES
from analysis.runner import get_jobs, is_running, is_done, start_analysis
from ai.client import call_ai
from ai.context import build_analysis_context


# ══════════════════════════════════════════════════════════════════════════════
# 进度/结果渲染工具
# ══════════════════════════════════════════════════════════════════════════════

def _show_job_progress(key: str, title: str):
    """显示后台任务的实时进度"""
    jobs = get_jobs(st.session_state)
    job = jobs.get(key, {})
    status = job.get("status", "")
    progress = job.get("progress", [])

    if status == "running":
        label = f"⏳ {title}..."
        with st.status(label, expanded=True, state="running"):
            for msg in progress:
                st.write(msg)
    elif status == "done" and job.get("error"):
        with st.status(f"❌ {title}失败", expanded=True, state="error"):
            for msg in progress:
                st.write(msg)


def _show_analysis_result(key: str, title: str, icon: str):
    """显示分析结果：运行中显示进度，完成显示结果"""
    analyses = st.session_state.get("analyses", {})
    content = analyses.get(key, "")

    if is_running(st.session_state, key):
        _show_job_progress(key, title)
    elif content:
        name = st.session_state.get("stock_name", "")
        st.markdown(f"#### {icon} {name} · {title}结果")
        with st.container(border=True):
            st.markdown(content)
    else:
        st.info(f"{title}尚未执行，点击上方按钮开始分析")


# ══════════════════════════════════════════════════════════════════════════════
# 主展示函数
# ══════════════════════════════════════════════════════════════════════════════

def show_completed_results(client=None, cfg=None, model_name=""):
    """根据 active_tab 展示对应内容"""
    name     = st.session_state.get("stock_name", "")
    tscode   = st.session_state.get("stock_code", "")
    analyses = st.session_state.get("analyses", {})
    active_tab = st.session_state.get("active_tab", "")

    if not name or not active_tab:
        return

    st.markdown("---")

    if active_tab == "expectation":
        _show_analysis_result("expectation", "预期差分析", "🔍")

    elif active_tab == "trend":
        _show_analysis_result("trend", "K线趋势研判", "📈")

    elif active_tab == "similarity":
        _show_similarity_section(name, tscode)

    elif active_tab == "fundamentals":
        _show_analysis_result("fundamentals", "基本面分析", "📋")

    elif active_tab == "moe":
        _show_moe_tab(client, cfg, model_name)

    elif active_tab == "all":
        _show_all_tab(client, cfg, model_name)

    elif active_tab == "qa":
        _render_free_question(client, cfg, model_name, name, tscode,
                              st.session_state.get("stock_info", {}), analyses)


def _show_moe_tab(client, cfg, model_name):
    """MoE 辩论 tab"""
    analyses = st.session_state.get("analyses", {})
    moe_done = bool(st.session_state.get("moe_results", {}).get("done"))

    if is_running(st.session_state, "moe"):
        _show_job_progress("moe", "MoE 多方辩论")
    elif moe_done:
        _render_moe_results()
    else:
        # 检查前置条件
        missing = []
        if not analyses.get("expectation"): missing.append("预期差分析")
        if not analyses.get("trend"):       missing.append("趋势分析")
        if not analyses.get("fundamentals"): missing.append("基本面分析")

        if missing:
            running_keys = [k for k in ["expectation", "trend", "fundamentals"]
                           if is_running(st.session_state, k)]
            if running_keys:
                st.info(f"前置分析正在进行中，完成后可启动 MoE 辩论")
                _show_running_summary()
            else:
                st.warning(f"MoE 辩论需要先完成：{'、'.join(missing)}")
        else:
            # 前三项都完成了，自动启动 MoE
            if client and not is_running(st.session_state, "moe"):
                start_analysis(st.session_state, "moe", client, cfg, model_name)
                time.sleep(0.5)
                st.rerun()


def _show_all_tab(client, cfg, model_name):
    """一键分析 tab — 显示所有分析的状态"""
    analyses = st.session_state.get("analyses", {})
    moe_done = bool(st.session_state.get("moe_results", {}).get("done"))

    # 显示每项分析状态
    items = [
        ("expectation", "预期差分析", "🔍"),
        ("trend", "K线趋势研判", "📈"),
        ("fundamentals", "基本面分析", "📋"),
        ("moe", "MoE辩论", "🎯"),
    ]

    for key, title, icon in items:
        if key == "moe":
            done = moe_done
        else:
            done = bool(analyses.get(key))

        if is_running(st.session_state, key):
            _show_job_progress(key, title)
        elif done:
            if key == "moe":
                _render_moe_results()
            else:
                content = analyses.get(key, "")
                if content:
                    name = st.session_state.get("stock_name", "")
                    st.markdown(f"#### {icon} {name} · {title}结果")
                    with st.container(border=True):
                        st.markdown(content)

    # 三项都完成且 MoE 未启动 → 自动启动 MoE
    all_three_done = all(analyses.get(k) for k in ["expectation", "trend", "fundamentals"])
    if all_three_done and not moe_done and not is_running(st.session_state, "moe") and client:
        start_analysis(st.session_state, "moe", client, cfg, model_name)
        time.sleep(0.5)
        st.rerun()


def _show_running_summary():
    """显示正在运行的任务列表"""
    jobs = get_jobs(st.session_state)
    names = {"expectation": "预期差分析", "trend": "K线趋势", "fundamentals": "基本面", "moe": "MoE辩论"}
    for key, name in names.items():
        job = jobs.get(key, {})
        if job.get("status") == "running":
            progress = job.get("progress", [])
            last_msg = progress[-1] if progress else "启动中..."
            st.caption(f"⏳ {name}：{last_msg}")


def _render_moe_results():
    moe = st.session_state.get("moe_results", {})
    if not moe.get("done"):
        return
    name = st.session_state.get("stock_name", "")
    st.markdown(f"#### 🎯 {name} · MoE 辩论裁决结果")
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


def _render_free_question(client, cfg, model_name, name, tscode, info, analyses):
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
        if not client:
            st.warning("AI 模型不可用，请检查 API Key")
            return

        with st.status("💬 正在回答你的问题...", expanded=True) as status:
            st.write(f"📡 正在连接 {model_name}...")
            time.sleep(0.5)
            st.write("📎 整理已有分析上下文作为参考...")
            context = build_analysis_context(analyses, max_per_module=12)
            time.sleep(0.4)
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

            st.write("🌐 联网搜索最新信息...")
            time.sleep(0.4)
            st.write("🤖 AI 正在思考并组织回答...")
            result, err = call_ai(client, cfg, prompt, system=system, max_tokens=8000)

            if err:
                status.update(label="❌ 回答失败", state="error")
                st.error(f"回答失败：{err}")
                return
            st.write("📝 整理回答内容...")
            time.sleep(0.3)
            status.update(label="✅ 回答完成！", state="complete")

        qa_history = st.session_state.get("qa_history", [])
        qa_history.append({"question": question, "answer": result})
        st.session_state["qa_history"] = qa_history

    # 显示历史问答
    qa_history = st.session_state.get("qa_history", [])
    if qa_history:
        for i, item in enumerate(reversed(qa_history), 1):
            st.markdown(f"**🙋 问题 {len(qa_history) - i + 1}：** {item['question']}")
            with st.container(border=True):
                st.markdown(item["answer"])
            if i < len(qa_history):
                st.markdown("")


# ══════════════════════════════════════════════════════════════════════════════
# K线相似走势匹配
# ══════════════════════════════════════════════════════════════════════════════

def _show_similarity_section(name: str, tscode: str):
    """在 K线趋势 tab 下方展示历史相似走势匹配"""
    from data.similarity import find_similar, HISTORY_FILE
    from ui.charts import render_similar_case
    import os

    # 历史数据文件不存在则跳过
    if not os.path.exists(HISTORY_FILE):
        return

    price_df = st.session_state.get("price_df", pd.DataFrame())
    if price_df.empty or len(price_df) < 5:
        return

    st.markdown("---")
    st.markdown(f"#### 📐 历史相似走势匹配 · {name}")
    st.caption(
        "基于最近5个交易日的五维K线特征（涨跌幅 · 振幅 · 量能节奏 · 上影线 · 下影线），"
        "在全市场5年历史数据中搜索最相似的走势，并展示匹配段前后各10天的完整走势供参考。"
    )

    # 检查缓存
    cached = st.session_state.get("similarity_results")
    if cached and cached.get("ts_code") == tscode:
        _render_similarity_results(cached["results"])
        return

    if st.button("🔍 开始匹配历史走势", type="primary", key="btn_similarity"):
        with st.status("📐 正在全市场搜索相似走势...", expanded=True) as status:
            st.write("📊 加载全市场5年日线数据（首次较慢）...")
            st.write("🔢 提取目标股票五维K线特征...")
            st.write(f"🔍 在5400+只股票中逐一滑窗匹配...")

            results = find_similar(
                target_df=price_df,
                k_days=5,
                top_n=3,
                context_days=10,
                exclude_code=tscode,
                exclude_recent_days=60,
            )

            if results:
                st.write(f"✅ 找到 {len(results)} 个高度相似的历史案例！")
                status.update(label="✅ 匹配完成！", state="complete")
            else:
                st.write("未找到足够相似的历史走势")
                status.update(label="⚠️ 未找到匹配", state="complete")

        # 缓存结果
        st.session_state["similarity_results"] = {
            "ts_code": tscode,
            "results": results,
        }

        if results:
            _render_similarity_results(results)


def _render_similarity_results(results: list):
    """渲染相似走势匹配结果"""
    from ui.charts import render_similar_case

    if not results:
        st.info("未找到足够相似的历史走势案例")
        return

    # 后续走势统计
    returns = [r["subsequent_return"] for r in results if r["subsequent_return"] is not None]
    if returns:
        avg_ret = sum(returns) / len(returns)
        up_count = sum(1 for r in returns if r > 0)
        color = "🟢" if avg_ret > 0 else "🔴"
        st.markdown(
            f"**历史参考：** Top {len(results)} 相似案例中，"
            f"{up_count} 个后续上涨、{len(returns) - up_count} 个下跌，"
            f"平均后续涨跌 {color} **{avg_ret:+.1f}%**"
        )
        st.caption("⚠️ 历史走势不代表未来表现，仅供参考")

    for i, case in enumerate(results, 1):
        render_similar_case(case, i)
