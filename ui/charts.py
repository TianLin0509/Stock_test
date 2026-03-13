"""K线图渲染 — 同花顺经典风格（红涨绿跌）"""

import numpy as np
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data.tushare_client import to_code6


# ══════════════════════════════════════════════════════════════════════════════
# 同花顺经典配色
# ══════════════════════════════════════════════════════════════════════════════
_UP     = "#ee3333"   # 涨 — 同花顺红
_DOWN   = "#00aa3b"   # 跌 — 同花顺绿
_MA_CLR = {           # 均线经典色
    5:  "#e8a633",    # MA5  — 黄
    10: "#33a3dc",    # MA10 — 蓝
    20: "#ee33ee",    # MA20 — 紫
    30: "#33ee33",    # MA30 — 绿
    60: "#aaaaaa",    # MA60 — 灰（主图用）
}
_BG      = "#1b1b1b"  # 深色背景
_GRID    = "#2a2a2a"  # 网格
_TEXT    = "#cccccc"   # 文字
_MATCH_BORDER = "rgba(238,51,51,0.4)"
_MATCH_BG     = "rgba(238,51,51,0.06)"


def render_kline(df: pd.DataFrame, name: str, ts_code: str) -> None:
    """主页 K 线图（同花顺经典暗色风格）"""
    if df.empty:
        st.warning("⚠️ 暂无K线数据")
        return
    d = df.copy()
    # 使用连续序号作为 x 轴，消除周末/节假日空档
    d = d.reset_index(drop=True)
    x_idx = list(range(len(d)))
    tick_vals = x_idx[::max(1, len(d)//8)]
    tick_text = [d.iloc[i]["日期"] if i < len(d) else "" for i in tick_vals]

    for p in [5, 10, 20, 30, 60]:
        d[f"MA{p}"] = d["收盘"].rolling(p).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=[0.72, 0.28])

    fig.add_trace(go.Candlestick(
        x=x_idx, open=d["开盘"], high=d["最高"],
        low=d["最低"], close=d["收盘"], name="K线",
        increasing=dict(line=dict(color=_UP, width=1), fillcolor=_UP),
        decreasing=dict(line=dict(color=_DOWN, width=1), fillcolor=_DOWN),
        whiskerwidth=0.4,
    ), row=1, col=1)

    for p, clr in [(5, _MA_CLR[5]), (20, _MA_CLR[20]), (60, _MA_CLR[60])]:
        fig.add_trace(go.Scatter(
            x=x_idx, y=d[f"MA{p}"], name=f"MA{p}",
            line=dict(color=clr, width=1.3), mode="lines",
        ), row=1, col=1)

    colors = [_UP if c >= o else _DOWN for c, o in zip(d["收盘"], d["开盘"])]
    fig.add_trace(go.Bar(x=x_idx, y=d["成交量"], name="成交量",
                          marker_color=colors, opacity=0.6), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x_idx, y=d["成交量"].rolling(5).mean(), name="量MA5",
        line=dict(color=_MA_CLR[5], width=1.2), mode="lines", opacity=0.85,
    ), row=2, col=1)

    _apply_ths_layout(fig, f"{name}（{to_code6(ts_code)}）日K线", 440,
                      tick_vals, tick_text, show_legend=True)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "responsive": True,
                            "scrollZoom": False})


# ══════════════════════════════════════════════════════════════════════════════
# 相似走势案例 K 线图（含目标股叠加对比）
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_date(d) -> str:
    if isinstance(d, (float, int, np.floating, np.integer)) and d > 19000000:
        di = int(d)
        return f"{di // 10000}-{di % 10000 // 100:02d}-{di % 100:02d}"
    return str(d)


def render_similar_case(case: dict, idx: int, target_df: pd.DataFrame = None,
                        k_days: int = 10) -> None:
    """
    渲染单个相似走势案例 — 同花顺暗色风格 + 目标股叠加对比
    """
    ctx = case["context_df"].copy()
    if ctx.empty:
        return

    code = case["ts_code"]
    stock_name = case.get("stock_name", "") or code
    sim = case["similarity"]
    kline_sim = case.get("kline_similarity", sim)
    vol_sim = case.get("vol_similarity", 0)
    start_d = _fmt_date(case["match_start_date"])
    end_d = _fmt_date(case["match_end_date"])
    ret = case["subsequent_return"]

    ret_text = f"后续走势 **{ret:+.1f}%**" if ret is not None else "后续数据不足"
    ret_color = ("🔴" if ret > 0 else "🟢" if ret < 0 else "⚪") if ret is not None else "⚪"

    st.markdown(f"""
**案例 {idx}：{stock_name}（{code}）** &nbsp;
匹配区间 `{start_d}` ~ `{end_d}` &nbsp;
综合 **{sim}%** &nbsp;|&nbsp; K线 **{kline_sim}%** &nbsp;|&nbsp;
成交量 **{vol_sim}%** &nbsp; {ret_color} {ret_text}
""")

    detail = case.get("feature_detail", {})
    if detail:
        labels = {"pct_chg": "涨跌形态", "amplitude": "K线振幅", "vol_chg": "量能节奏",
                  "upper_shadow": "上影线", "lower_shadow": "下影线"}
        parts = [f"{labels.get(k, k)} {v}%" for k, v in detail.items()]
        st.caption(" · ".join(parts))

    # ── 准备数据 ─────────────────────────────────────────────────────────
    ctx = ctx.reset_index(drop=True)
    match_mask = ctx["is_match"].values
    n = len(ctx)
    x_idx = list(range(n))

    # 日期标签
    date_labels = [_fmt_date(d) for d in ctx["trade_date"].values]
    tick_vals = x_idx[::max(1, n // 6)]
    tick_text = [date_labels[i] for i in tick_vals]

    closes = ctx["close"].values.astype(float)
    opens = ctx["open"].values.astype(float)

    # 计算均线
    ma_data = {}
    for p in [5, 10, 20, 30]:
        if len(closes) >= p:
            ma_data[p] = pd.Series(closes).rolling(p).mean().values

    # ── 匹配段索引 ────────────────────────────────────────────────────────
    match_indices = [i for i, m in enumerate(match_mask) if m]
    match_start_idx = match_indices[0] if match_indices else 0
    match_end_idx = match_indices[-1] if match_indices else n - 1

    # ── 构建图表 ─────────────────────────────────────────────────────────
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.70, 0.30])

    # 案例股 K线
    fig.add_trace(go.Candlestick(
        x=x_idx, open=ctx["open"], high=ctx["high"],
        low=ctx["low"], close=ctx["close"],
        name=stock_name,
        increasing=dict(line=dict(color=_UP, width=1), fillcolor=_UP),
        decreasing=dict(line=dict(color=_DOWN, width=1), fillcolor=_DOWN),
        whiskerwidth=0.4,
    ), row=1, col=1)

    # 均线
    for p in [5, 10, 20, 30]:
        if p in ma_data:
            fig.add_trace(go.Scatter(
                x=x_idx, y=ma_data[p], name=f"MA{p}",
                line=dict(color=_MA_CLR[p], width=1.1), mode="lines",
            ), row=1, col=1)

    # ── 叠加目标股 K线（仅匹配段区域）──────────────────────────────────
    if target_df is not None and len(target_df) >= k_days:
        tgt = target_df.tail(k_days).reset_index(drop=True)
        tgt_close = tgt["收盘"].values.astype(float)
        tgt_open = tgt["开盘"].values.astype(float)
        tgt_high = tgt["最高"].values.astype(float)
        tgt_low = tgt["最低"].values.astype(float)
        tgt_vol = tgt["成交量"].values.astype(float)

        # 价格归一化：将目标股价格映射到案例股匹配段的价格范围
        case_match_close = closes[match_start_idx:match_end_idx + 1]
        case_match_high = ctx["high"].values[match_start_idx:match_end_idx + 1].astype(float)
        case_match_low = ctx["low"].values[match_start_idx:match_end_idx + 1].astype(float)

        if len(case_match_close) > 0 and len(tgt_close) > 0:
            # 用价格范围做线性映射
            case_min = float(case_match_low.min())
            case_max = float(case_match_high.max())
            tgt_min = float(tgt_low.min())
            tgt_max = float(tgt_high.max())
            tgt_range = tgt_max - tgt_min if tgt_max != tgt_min else 1
            case_range = case_max - case_min if case_max != case_min else 1

            def _map_price(arr):
                return (arr - tgt_min) / tgt_range * case_range + case_min

            mapped_open = _map_price(tgt_open)
            mapped_high = _map_price(tgt_high)
            mapped_low = _map_price(tgt_low)
            mapped_close = _map_price(tgt_close)

            # x 坐标对齐到匹配段
            tgt_x = list(range(match_start_idx, match_start_idx + len(tgt_close)))

            # 目标股 K线（半透明蓝色叠加）
            fig.add_trace(go.Candlestick(
                x=tgt_x, open=mapped_open, high=mapped_high,
                low=mapped_low, close=mapped_close,
                name="目标股(叠加)",
                increasing=dict(line=dict(color="rgba(65,105,225,0.7)", width=1.5),
                                fillcolor="rgba(65,105,225,0.25)"),
                decreasing=dict(line=dict(color="rgba(65,105,225,0.7)", width=1.5),
                                fillcolor="rgba(30,60,160,0.25)"),
                whiskerwidth=0.3,
            ), row=1, col=1)

            # 成交量归一化叠加
            case_match_vol = ctx["vol"].values[match_start_idx:match_end_idx + 1].astype(float)
            if case_match_vol.max() > 0 and tgt_vol.max() > 0:
                vol_scale = case_match_vol.max() / tgt_vol.max()
                mapped_vol = tgt_vol * vol_scale
                tgt_vol_colors = ["rgba(65,105,225,0.45)" if c >= o else "rgba(30,60,160,0.45)"
                                  for c, o in zip(tgt_close, tgt_open)]
                fig.add_trace(go.Bar(
                    x=tgt_x, y=mapped_vol, name="目标股成交量",
                    marker_color=tgt_vol_colors, opacity=0.5,
                ), row=2, col=1)

    # 匹配段背景高亮
    if match_indices:
        fig.add_vrect(
            x0=match_start_idx - 0.5, x1=match_end_idx + 0.5,
            fillcolor=_MATCH_BG, line_width=1, line_color=_MATCH_BORDER,
            annotation_text="匹配段", annotation_position="top left",
            annotation_font_size=10, annotation_font_color="#ff6666",
            row=1, col=1,
        )
        fig.add_vrect(
            x0=match_start_idx - 0.5, x1=match_end_idx + 0.5,
            fillcolor=_MATCH_BG, line_width=0,
            row=2, col=1,
        )

    # 案例股成交量
    bar_colors = [_UP if c >= o else _DOWN for c, o in zip(closes, opens)]
    fig.add_trace(go.Bar(
        x=x_idx, y=ctx["vol"], name="成交量",
        marker_color=bar_colors, opacity=0.65,
    ), row=2, col=1)

    _apply_ths_layout(fig, None, 420, tick_vals, tick_text, show_legend=True)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "responsive": True,
                            "scrollZoom": False})


# ══════════════════════════════════════════════════════════════════════════════
# 同花顺经典布局
# ══════════════════════════════════════════════════════════════════════════════

def _apply_ths_layout(fig, title, height, tick_vals, tick_text, show_legend=False):
    """统一应用同花顺经典暗色布局"""
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>" if title else "",
                   font=dict(size=12, color=_TEXT)) if title else {},
        template="plotly_dark",
        height=height, autosize=True,
        xaxis_rangeslider_visible=False,
        plot_bgcolor=_BG, paper_bgcolor="#141414",
        font=dict(family="'Noto Sans SC','Microsoft YaHei',sans-serif",
                  color=_TEXT, size=10),
        legend=dict(
            orientation="h", y=1.06, x=0,
            font=dict(size=9, color=_TEXT),
            bgcolor="rgba(0,0,0,0)",
        ) if show_legend else dict(visible=False),
        margin=dict(t=35 if title else 25, b=10, l=5, r=5),
        hovermode="x unified",
        dragmode=False,
        bargap=0.15,
    )
    # 连续 x 轴（用序号 + 自定义 tick 显示日期）
    for ax_name in ["xaxis", "xaxis2"]:
        fig.update_layout(**{
            ax_name: dict(
                type="linear",
                tickvals=tick_vals, ticktext=tick_text,
                gridcolor=_GRID, gridwidth=0.5,
                zeroline=False, showgrid=True,
                tickfont=dict(size=9, color="#888"),
            )
        })
    fig.update_yaxes(gridcolor=_GRID, gridwidth=0.5, zeroline=False,
                     tickfont=dict(size=9, color="#888"))
