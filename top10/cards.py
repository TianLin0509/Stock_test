"""Top 10 精简卡片 — 内嵌到 Stock_test 的折叠区"""

import math
import pandas as pd
import streamlit as st


def show_top10_cards(df: pd.DataFrame):
    """展示精简版 Top 10 推荐股票卡片，含"分析此股"按钮"""
    if df.empty:
        st.info("暂无推荐结果")
        return

    top = df.head(10)

    for i, (_, row) in enumerate(top.iterrows(), 1):
        score = row.get("综合评分", 0)
        name = row.get("股票名称", "")
        code = row.get("代码", "")
        price = row.get("最新价", 0)
        change = row.get("涨跌幅", 0)
        advice = row.get("短线建议", "")
        industry = row.get("行业", "")
        s_fund = row.get("基本面")
        s_theme = row.get("题材热度")
        s_tech = row.get("技术面")

        # 颜色
        if score >= 8:
            border_color = "#22c55e"
            badge_bg = "#f0fdf4"
            badge_color = "#16a34a"
        elif score >= 6:
            border_color = "#6366f1"
            badge_bg = "#eef2ff"
            badge_color = "#6366f1"
        else:
            border_color = "#f97316"
            badge_bg = "#fff7ed"
            badge_color = "#c2410c"

        _change_safe = change if (isinstance(change, float) and not math.isnan(change)) else 0.0
        change_color = "#22c55e" if _change_safe >= 0 else "#ef4444"
        change_sign = "+" if _change_safe >= 0 else ""
        price_str = f"{price:.2f}" if isinstance(price, (int, float)) and not (isinstance(price, float) and math.isnan(price)) else str(price)
        change_str = f"{change_sign}{_change_safe:.2f}"

        # 短线建议标签
        advice_map = {
            "强烈推荐": ("#dc2626", "#fef2f2", "🔥 强烈推荐"),
            "推荐": ("#16a34a", "#f0fdf4", "👍 推荐"),
            "观望": ("#d97706", "#fffbeb", "👀 观望"),
            "回避": ("#6b7280", "#f3f4f6", "⛔ 回避"),
        }
        adv_color, adv_bg, adv_text = advice_map.get(advice, ("#6b7280", "#f3f4f6", ""))
        advice_html = f"""<span style="
            background:{adv_bg}; color:{adv_color};
            border-radius:50px; padding:2px 10px;
            font-weight:700; font-size:0.78rem; margin-left:10px;
        ">{adv_text}</span>""" if adv_text else ""

        # 行业标签
        industry_html = f"""<span style="
            background:#f0f9ff; color:#0369a1;
            border-radius:50px; padding:2px 8px;
            font-size:0.72rem; margin-left:6px;
        ">{industry}</span>""" if industry else ""

        # 子评分进度条
        def _bar(label, val, color):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return ""
            pct = min(val * 10, 100)
            return f"""<div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
                <span style="font-size:0.75rem; color:#6b7280; min-width:56px;">{label}</span>
                <div style="flex:1; background:#f1f5f9; border-radius:4px; height:8px; overflow:hidden;">
                    <div style="width:{pct}%; background:{color}; height:100%; border-radius:4px;"></div>
                </div>
                <span style="font-size:0.75rem; color:#374151; min-width:28px; text-align:right;">{val:.0f}</span>
            </div>"""

        sub_bars = _bar("基本面", s_fund, "#3b82f6") + _bar("题材", s_theme, "#f59e0b") + _bar("技术面", s_tech, "#22c55e")

        # 量化预评分标签
        quant_total = row.get("量化总分")
        quant_signal = row.get("量化信号", "")
        quant_html = ""
        if quant_total and not (isinstance(quant_total, float) and math.isnan(quant_total)):
            q_color = "#16a34a" if quant_total >= 65 else "#f59e0b" if quant_total >= 50 else "#ef4444"
            quant_html = f"""<div style="margin-top:6px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:0.72rem; color:#6b7280;">量化预评分</span>
                <span style="background:{q_color}15; color:{q_color}; border-radius:4px;
                    padding:1px 8px; font-size:0.72rem; font-weight:700;">{int(quant_total)}/100 {quant_signal}</span>
            </div>"""

        sub_section = f'<div style="margin-top:8px;">{sub_bars}{quant_html}</div>' if (sub_bars or quant_html) else ""

        st.markdown(f"""<div style="
            background: #fff;
            border: 2px solid {border_color};
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 0.4rem 0;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        ">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
                <div>
                    <span style="font-size:1.2rem; font-weight:800; color:#1e1b4b;">
                        #{i} {name}
                    </span>
                    <span style="font-size:0.82rem; color:#6b7280; margin-left:8px;">{code}</span>
                    {industry_html}
                    {advice_html}
                </div>
                <div style="
                    background:{badge_bg}; color:{badge_color};
                    border-radius:50px; padding:4px 14px;
                    font-weight:800; font-size:1rem;
                ">{score}/10</div>
            </div>
            <div style="display:flex; gap:16px; font-size:0.85rem; color:#6b7280;">
                <span>💰 {price_str}元</span>
                <span style="color:{change_color}; font-weight:600;">{change_str}%</span>
            </div>
            {sub_section}
        </div>""", unsafe_allow_html=True)

        # "分析此股"按钮
        if st.button(f"🔍 深度分析 {name}", key=f"top10_pick_{code}", use_container_width=True):
            st.session_state["_top10_pick"] = code


def show_progress(job: dict):
    """显示后台任务进度"""
    if not job:
        return

    status = job.get("status", "")
    progress = job.get("progress", [])
    current = job.get("current", 0)
    total = job.get("total", 1)

    if status == "running":
        pct = current / total if total > 0 else 0
        st.progress(pct, text=f"分析进度：{current}/{total}")
        with st.status("🔍 AI 正在深度分析...", expanded=True, state="running"):
            for msg in progress[-8:]:
                st.write(msg)
    elif status == "done" and job.get("error"):
        st.error(f"分析失败：{job['error']}")
    elif status == "done":
        st.success(f"✅ 分析完成！共评分 {total} 只股票")
