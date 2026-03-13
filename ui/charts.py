"""K线图渲染"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data.tushare_client import to_code6


def render_kline(df: pd.DataFrame, name: str, ts_code: str) -> None:
    if df.empty:
        st.warning("⚠️ 暂无K线数据，请检查股票代码或 Tushare 连接状态")
        return
    d = df.copy()
    for p in [5, 20, 60]:
        d[f"MA{p}"] = d["收盘"].rolling(p).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=[0.72, 0.28])

    fig.add_trace(go.Candlestick(
        x=d["日期"], open=d["开盘"], high=d["最高"],
        low=d["最低"], close=d["收盘"], name="K线",
        increasing=dict(line=dict(color="#22c55e", width=1.2), fillcolor="#22c55e"),
        decreasing=dict(line=dict(color="#ef4444", width=1.2), fillcolor="#ef4444"),
        whiskerwidth=0.5,
    ), row=1, col=1)

    for ma, clr in [("MA5", "#f97316"), ("MA20", "#6366f1"), ("MA60", "#a855f7")]:
        fig.add_trace(go.Scatter(x=d["日期"], y=d[ma], name=ma,
                                  line=dict(color=clr, width=1.6), mode="lines"),
                      row=1, col=1)

    colors = ["#22c55e" if c >= o else "#ef4444"
              for c, o in zip(d["收盘"], d["开盘"])]
    fig.add_trace(go.Bar(x=d["日期"], y=d["成交量"], name="成交量",
                          marker_color=colors, opacity=0.55), row=2, col=1)
    fig.add_trace(go.Scatter(x=d["日期"], y=d["成交量"].rolling(5).mean(), name="量MA5",
                              line=dict(color="#f97316", width=1.5), mode="lines",
                              opacity=0.85), row=2, col=1)

    fig.update_layout(
        title=dict(text=f"<b>{name}（{to_code6(ts_code)}）</b>  日K线",
                   font=dict(family="Nunito,sans-serif", size=13, color="#6b7280")),
        template="plotly_white", height=440, autosize=True,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#fafbff", paper_bgcolor="#ffffff",
        font=dict(family="Nunito,sans-serif", color="#6b7280", size=11),
        legend=dict(orientation="h", y=1.05, x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=45, b=10, l=5, r=5),
        hovermode="x unified",
        dragmode=False,
    )
    fig.update_xaxes(gridcolor="#e5e7eb", gridwidth=0.5, zeroline=False, nticks=8)
    fig.update_yaxes(gridcolor="#e5e7eb", gridwidth=0.5)
    st.plotly_chart(fig, use_container_width=True,
                    config={
                        "displayModeBar": False,
                        "responsive": True,
                        "scrollZoom": False,
                    })


def _fmt_date(d) -> str:
    """float 20210315.0 → '2021-03-15'"""
    if isinstance(d, (float, int)) and d > 19000000:
        di = int(d)
        return f"{di // 10000}-{di % 10000 // 100:02d}-{di % 100:02d}"
    return str(d)


# 中国风配色：红涨绿跌
_UP_COLOR   = "#cf222e"   # 涨 — 中国红
_DOWN_COLOR = "#1a7f37"   # 跌 — 墨绿
_UP_FILL    = "#cf222e"
_DOWN_FILL  = "#1a7f37"
_MATCH_BG   = "rgba(207,34,46,0.08)"   # 匹配段浅红底
_MATCH_BAR  = "#c9510c"   # 匹配段量柱 — 橙红


def render_similar_case(case: dict, idx: int) -> None:
    """
    渲染单个相似走势案例的 K 线图（中国风红涨绿跌）
    """
    ctx = case["context_df"].copy()
    if ctx.empty:
        return

    code = case["ts_code"]
    stock_name = case.get("stock_name", "") or code
    sim  = case["similarity"]
    kline_sim = case.get("kline_similarity", sim)
    vol_sim   = case.get("vol_similarity", 0)
    start_d = _fmt_date(case["match_start_date"])
    end_d   = _fmt_date(case["match_end_date"])
    ret     = case["subsequent_return"]

    ret_text = f"后续走势 **{ret:+.1f}%**" if ret is not None else "后续数据不足"
    if ret is not None:
        ret_color = "🔴" if ret > 0 else "🟢" if ret < 0 else "⚪"  # 中国风：红涨绿跌
    else:
        ret_color = "⚪"

    # 标题行：名称 + 代码 + 区间 + 综合/K线/成交量匹配度
    st.markdown(f"""
**案例 {idx}：{stock_name}（{code}）** &nbsp;
匹配区间 `{start_d}` ~ `{end_d}` &nbsp;
综合匹配 **{sim}%** &nbsp;|&nbsp; K线匹配 **{kline_sim}%** &nbsp;|&nbsp;
成交量匹配 **{vol_sim}%** &nbsp; {ret_color} {ret_text}
""")

    # 五维分项得分
    detail = case.get("feature_detail", {})
    if detail:
        labels = {
            "pct_chg": "涨跌形态",
            "amplitude": "K线振幅",
            "vol_chg": "量能节奏",
            "upper_shadow": "上影线",
            "lower_shadow": "下影线",
        }
        parts = [f"{labels.get(k, k)} {v}%" for k, v in detail.items()]
        st.caption(" · ".join(parts))

    # ── K线图 + 成交量 ─────────────────────────────────────────────────
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.70, 0.30])

    match_mask = ctx["is_match"].values
    dates = [_fmt_date(d) for d in ctx["trade_date"].values]

    # K 线（中国风：红涨绿跌）
    fig.add_trace(go.Candlestick(
        x=dates, open=ctx["open"], high=ctx["high"],
        low=ctx["low"], close=ctx["close"], name="K线",
        increasing=dict(line=dict(color=_UP_COLOR, width=1), fillcolor=_UP_FILL),
        decreasing=dict(line=dict(color=_DOWN_COLOR, width=1), fillcolor=_DOWN_FILL),
        whiskerwidth=0.4,
    ), row=1, col=1)

    # MA5 均线
    closes = ctx["close"].values.astype(float)
    if len(closes) >= 5:
        ma5 = pd.Series(closes).rolling(5).mean().values
        fig.add_trace(go.Scatter(
            x=dates, y=ma5, name="MA5",
            line=dict(color="#e8590c", width=1.2, dash="dot"), mode="lines",
        ), row=1, col=1)

    # 匹配段背景高亮
    match_dates = [d for d, m in zip(dates, match_mask) if m]
    if len(match_dates) >= 2:
        fig.add_vrect(
            x0=match_dates[0], x1=match_dates[-1],
            fillcolor=_MATCH_BG, line_width=1,
            line_color="rgba(207,34,46,0.25)",
            annotation_text="匹配段", annotation_position="top left",
            annotation_font_size=10, annotation_font_color=_UP_COLOR,
            row=1, col=1,
        )
        fig.add_vrect(
            x0=match_dates[0], x1=match_dates[-1],
            fillcolor=_MATCH_BG, line_width=0,
            row=2, col=1,
        )

    # 成交量柱
    bar_colors = []
    for c, o, m in zip(ctx["close"], ctx["open"], match_mask):
        if m:
            bar_colors.append(_MATCH_BAR if c >= o else "#2da44e")
        else:
            bar_colors.append(_UP_COLOR if c >= o else _DOWN_COLOR)
    fig.add_trace(go.Bar(
        x=dates, y=ctx["vol"], name="成交量",
        marker_color=bar_colors, opacity=0.7,
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_white", height=380, autosize=True,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#fffaf5", paper_bgcolor="#ffffff",
        font=dict(family="'Noto Sans SC',sans-serif", color="#57534e", size=10),
        legend=dict(orientation="h", y=1.06, x=0,
                    font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=30, b=10, l=5, r=5),
        showlegend=False,
        hovermode="x unified",
        dragmode=False,
    )
    fig.update_xaxes(gridcolor="#f5e6d3", gridwidth=0.5, zeroline=False)
    fig.update_yaxes(gridcolor="#f5e6d3", gridwidth=0.5)

    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "responsive": True,
                            "scrollZoom": False})
