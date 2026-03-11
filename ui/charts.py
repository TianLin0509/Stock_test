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
