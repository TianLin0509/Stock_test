"""Tab 3: 📈 回测战绩 — 从 streamlit_app.py 提取"""

import streamlit as st
import pandas as pd


def render_backtest_tab():
    """渲染回测战绩 Tab"""
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
    bt_df = cached_bt if cached_bt is not None else pd.DataFrame()

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
                "_code": a.get("stock_code", ""),
                "用户": a.get("username", ""),
                "模型": str(a.get("model", "")),
                "AI评级": rec["rating"],
                "收盘价": a.get("close", "—"),
            })
        if preview_rows:
            df_preview = pd.DataFrame(preview_rows[::-1])
            # 同日期+股票+模型去重，保留最新评级
            df_preview = df_preview.drop_duplicates(
                subset=["日期", "_code", "模型"], keep="first"
            )
            df_preview = df_preview.drop(columns=["_code"])
            st.dataframe(df_preview, use_container_width=True, hide_index=True)
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
        rename = {"rating": "AI评级", "count": "次数",
                  "avg_5d": "5日平均%", "avg_10d": "10日平均%", "avg_20d": "20日平均%"}
        rating_df = rating_df.rename(columns=rename)
        st.dataframe(rating_df, use_container_width=True, hide_index=True)

    # ── 收益分布图 ───────────────────────────────────────────
    import plotly.graph_objects as go

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
                pass
            else:
                cum_ret += ret * 0.5
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
    dir_map = {"bullish": "🟢 看多", "bearish": "🔴 看空",
               "neutral": "🟡 中性", "unknown": "❓"}
    display_df["方向"] = display_df["方向"].map(dir_map)
    display_df["模型"] = display_df["模型"].apply(lambda x: str(x)[:12])
    display_df = display_df.sort_values("日期", ascending=False)

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.caption("⚠️ 回测结果仅供参考，历史表现不代表未来收益。AI 分析存在局限性，请独立判断。")
