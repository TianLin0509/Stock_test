#!/usr/bin/env python3
"""
📈 A股智能投研助手 v2
Powered by Claude AI + Tushare
"""

import streamlit as st
import anthropic
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json, re

# ══════════════════════════════════════════════════════════════════════════════
# TUSHARE INIT  — token hardcoded，直接用
# ══════════════════════════════════════════════════════════════════════════════
import tushare as ts
ts.set_token("96e4ecf7246cddb2f781283bb1bbf7e45c6277a0e818a6ab1b4dcc31ea84")
pro = ts.pro_api()
pro._DataApi__http_url = "http://lianghua.nanyangqiankun.top"

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="A股投研小助手 🌸",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS — 浅色可爱风  Soft Pastel × Friendly
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700&display=swap');

:root {
  --bg:        #f6f8ff;
  --bg-card:   #ffffff;
  --bg-soft:   #eef2ff;
  --border:    #dde3ff;
  --up:        #22c55e;
  --down:      #ef4444;
  --blue:      #6366f1;
  --blue-lt:   #eef2ff;
  --pink:      #ec4899;
  --pink-lt:   #fdf2f8;
  --teal:      #06b6d4;
  --teal-lt:   #ecfeff;
  --orange:    #f97316;
  --orange-lt: #fff7ed;
  --purple:    #a855f7;
  --purple-lt: #faf5ff;
  --text:      #1e1b4b;
  --text-mid:  #6b7280;
  --text-lo:   #9ca3af;
  --shadow:    0 2px 16px rgba(99,102,241,0.08);
  --shadow-md: 0 4px 24px rgba(99,102,241,0.12);
  --radius:    16px;
  --radius-sm: 10px;
}

html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  font-family: 'Noto Sans SC', 'PingFang SC', sans-serif;
  color: var(--text);
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text-mid) !important; }
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong { color: var(--blue) !important; }

/* ─── Main header ───────────────────────────────────── */
.app-header {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
  border-radius: var(--radius);
  padding: 1.8rem 2.2rem;
  margin-bottom: 1.4rem;
  position: relative;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(99,102,241,0.25);
}
.app-header::before {
  content: '📊 📈 💹 📉 🏦 💰 📊 📈 💹';
  position: absolute;
  top: 10px; right: -10px;
  font-size: 1.3rem;
  opacity: 0.15;
  letter-spacing: 0.5em;
  white-space: nowrap;
}
.app-header h1 {
  font-family: 'Nunito', sans-serif;
  font-size: 2rem;
  font-weight: 800;
  color: #fff;
  margin: 0;
  text-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.app-header p {
  color: rgba(255,255,255,0.82);
  font-size: 0.88rem;
  margin: 0.4rem 0 0;
  font-weight: 500;
}

/* ─── Cards ─────────────────────────────────────────── */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.4rem 1.6rem;
  margin: 0.7rem 0;
  box-shadow: var(--shadow);
}
.card h3 {
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--blue);
  margin: 0 0 1rem 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ─── Metric chips ───────────────────────────────────── */
.chip-row { display: flex; gap: 10px; flex-wrap: wrap; margin: 0.8rem 0; }
.chip {
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: 50px;
  padding: 5px 14px;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
.chip .lbl { color: var(--text-lo); font-weight: 500; margin-right: 4px; }
.chip.up   { background: #f0fdf4; border-color: #86efac; color: var(--up);   }
.chip.down { background: #fef2f2; border-color: #fca5a5; color: var(--down); }

/* ─── Tabs ───────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg-card) !important;
  border-radius: 50px !important;
  padding: 4px !important;
  border: 1px solid var(--border) !important;
  gap: 2px !important;
  box-shadow: var(--shadow) !important;
  width: fit-content !important;
}
.stTabs [data-baseweb="tab"] {
  border-radius: 50px !important;
  font-family: 'Nunito', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.85rem !important;
  color: var(--text-mid) !important;
  padding: 6px 20px !important;
  transition: all 0.2s !important;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  color: #fff !important;
  box-shadow: 0 2px 10px rgba(99,102,241,0.3) !important;
}

/* ─── MoE role blocks ────────────────────────────────── */
.role-card {
  border-radius: var(--radius);
  padding: 1.3rem 1.5rem;
  margin: 0.9rem 0;
  border: 1px solid;
  position: relative;
}
.role-badge {
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 3px 12px;
  border-radius: 50px;
  display: inline-block;
  margin-bottom: 0.8rem;
}
.role-content {
  font-size: 0.9rem;
  line-height: 1.8;
  white-space: pre-wrap;
  color: var(--text);
}

.r-trader      { background: #fff5f5; border-color: #fca5a5; }
.r-trader      .role-badge { background: #fee2e2; color: #dc2626; }

.r-inst        { background: #f0fdf4; border-color: #86efac; }
.r-inst        .role-badge { background: #dcfce7; color: #16a34a; }

.r-quant       { background: var(--blue-lt); border-color: #c7d2fe; }
.r-quant       .role-badge { background: #e0e7ff; color: var(--blue); }

.r-retail      { background: var(--orange-lt); border-color: #fed7aa; }
.r-retail      .role-badge { background: #ffedd5; color: var(--orange); }

.r-ceo {
  background: linear-gradient(135deg, var(--purple-lt) 0%, var(--pink-lt) 100%);
  border-color: #d8b4fe;
  box-shadow: 0 4px 24px rgba(168,85,247,0.12);
}
.r-ceo .role-badge {
  background: linear-gradient(135deg, var(--purple), var(--pink));
  color: #fff;
  box-shadow: 0 2px 8px rgba(168,85,247,0.3);
}

/* ─── Input & Button ──────────────────────────────────── */
.stTextInput input {
  border-radius: 50px !important;
  border: 2px solid var(--border) !important;
  background: var(--bg-card) !important;
  padding: 0.55rem 1.2rem !important;
  font-size: 0.95rem !important;
  transition: all 0.2s !important;
}
.stTextInput input:focus {
  border-color: var(--blue) !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
}
.stButton button {
  border-radius: 50px !important;
  font-family: 'Nunito', sans-serif !important;
  font-weight: 700 !important;
  font-size: 0.88rem !important;
  padding: 0.5rem 1.4rem !important;
  transition: all 0.2s !important;
}
.stButton button[kind="primary"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  border: none !important;
  color: #fff !important;
  box-shadow: 0 4px 14px rgba(99,102,241,0.3) !important;
}
.stButton button[kind="primary"]:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4) !important;
}

/* ─── Disclaimer ─────────────────────────────────────── */
.disclaimer {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: var(--radius-sm);
  padding: 0.7rem 1rem;
  font-size: 0.78rem;
  color: #c2410c;
  margin-top: 0.8rem;
  line-height: 1.6;
}

/* ─── Streamlit metrics ───────────────────────────────── */
[data-testid="metric-container"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  padding: 0.9rem 1rem !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.72rem !important;
  color: var(--text-lo) !important;
  font-weight: 600 !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Nunito', sans-serif !important;
  font-size: 1.15rem !important;
  font-weight: 800 !important;
  color: var(--text) !important;
}

/* ─── Content typography ─────────────────────────────── */
.analysis-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.6rem 1.8rem;
  box-shadow: var(--shadow);
  line-height: 1.8;
  font-size: 0.92rem;
}

hr { border-color: var(--border) !important; margin: 1rem 0 !important; }

/* ─── Sidebar niceties ───────────────────────────────── */
[data-testid="stSidebar"] .stTextInput input {
  border-radius: var(--radius-sm) !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Tushare code conversion
# ══════════════════════════════════════════════════════════════════════════════

def to_ts_code(code6: str) -> str:
    """'600519' → '600519.SH'  |  '000858' → '000858.SZ'"""
    code6 = code6.strip()
    if "." in code6:
        return code6.upper()
    if code6.startswith("6"):
        return f"{code6}.SH"
    if code6.startswith(("4", "8")):
        return f"{code6}.BJ"
    return f"{code6}.SZ"


def to_code6(ts_code: str) -> str:
    return ts_code.split(".")[0] if "." in ts_code else ts_code


def today() -> str:
    return datetime.now().strftime("%Y%m%d")


def ndays_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y%m%d")


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER — Tushare
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list() -> pd.DataFrame:
    """返回 columns: symbol(6位), name, ts_code"""
    try:
        df = pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,industry,area,market"
        )
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception as e:
        st.warning(f"股票列表获取失败: {e}")
        return pd.DataFrame()


def resolve_stock(query: str) -> tuple[str, str]:
    """输入 6位代码 或 中文名称 → (ts_code, name)"""
    query = query.strip()
    df = load_stock_list()
    if df.empty:
        # fallback: just construct ts_code
        code6 = re.sub(r"\D", "", query)
        return to_ts_code(code6), query

    # Try 6-digit code match
    if re.match(r"^\d{6}$", query):
        m = df[df["symbol"] == query]
        if not m.empty:
            return m.iloc[0]["ts_code"], m.iloc[0]["name"]
        return to_ts_code(query), query

    # Try name match
    m = df[df["name"].str.contains(query, na=False)]
    if not m.empty:
        return m.iloc[0]["ts_code"], m.iloc[0]["name"]

    # Try symbol partial
    m = df[df["symbol"].str.contains(query, na=False)]
    if not m.empty:
        return m.iloc[0]["ts_code"], m.iloc[0]["name"]

    return to_ts_code(re.sub(r"\D", "", query) or "000001"), query


@st.cache_data(ttl=600, show_spinner=False)
def get_basic_info(ts_code: str) -> dict:
    """基本信息：从 stock_basic + daily_basic 合并"""
    result = {}
    try:
        # Static info
        df_list = load_stock_list()
        if not df_list.empty:
            m = df_list[df_list["ts_code"] == ts_code]
            if not m.empty:
                row = m.iloc[0]
                result["名称"] = row.get("name", "")
                result["行业"] = row.get("industry", "")
                result["地区"] = row.get("area", "")
                result["市场"] = row.get("market", "")
    except Exception:
        pass

    try:
        # Dynamic info (latest trading day)
        df_db = pro.daily_basic(
            ts_code=ts_code,
            trade_date=today(),
            fields="ts_code,trade_date,close,pe,pe_ttm,pb,ps_ttm,total_mv,circ_mv,turnover_rate,volume_ratio"
        )
        if df_db is None or df_db.empty:
            # Try yesterday
            df_db = pro.daily_basic(
                ts_code=ts_code,
                start_date=ndays_ago(10),
                end_date=today(),
                fields="ts_code,trade_date,close,pe,pe_ttm,pb,ps_ttm,total_mv,circ_mv,turnover_rate,volume_ratio"
            )
            if df_db is not None and not df_db.empty:
                df_db = df_db.head(1)

        if df_db is not None and not df_db.empty:
            row = df_db.iloc[0]
            result["最新价(元)"]  = f"{row.get('close', 'N/A')}"
            result["市盈率TTM"]   = f"{row.get('pe_ttm', 'N/A')}"
            result["市净率PB"]    = f"{row.get('pb', 'N/A')}"
            result["市销率PS"]    = f"{row.get('ps_ttm', 'N/A')}"
            mv = row.get("total_mv")
            result["总市值(万元)"] = f"{float(mv):,.0f}" if mv else "N/A"
            result["换手率(%)"]   = f"{row.get('turnover_rate', 'N/A')}"
            result["量比"]        = f"{row.get('volume_ratio', 'N/A')}"
    except Exception as e:
        result["basic_info_err"] = str(e)

    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_price_df(ts_code: str, days: int = 140) -> pd.DataFrame:
    """日线K线数据，列名统一为中文"""
    try:
        df = pro.daily(
            ts_code=ts_code,
            start_date=ndays_ago(days),
            end_date=today(),
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df.rename(columns={
            "trade_date": "日期",
            "open":       "开盘",
            "high":       "最高",
            "low":        "最低",
            "close":      "收盘",
            "vol":        "成交量",
            "pct_chg":    "涨跌幅",
            "amount":     "成交额",
            "change":     "涨跌额",
        })
        return df
    except Exception as e:
        st.warning(f"K线数据获取失败: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_financial(ts_code: str) -> str:
    """财务核心指标 + 利润表"""
    parts = []
    # 财务指标
    try:
        df = pro.fina_indicator(
            ts_code=ts_code,
            fields="end_date,roe,roa,grossprofit_margin,netprofit_margin,"
                   "debt_to_assets,current_ratio,quick_ratio,"
                   "revenue_yoy,netprofit_yoy,basic_eps,bps,cfps"
        )
        if df is not None and not df.empty:
            parts.append("核心财务指标（近5期）：\n" + df.head(5).to_string(index=False))
    except Exception as e:
        parts.append(f"财务指标获取失败: {e}")

    # 利润表
    try:
        # Get latest report period
        rpt = (datetime.now().year - 1) * 10000 + 1231
        df2 = pro.income(
            ts_code=ts_code,
            start_date=str(rpt - 30000),
            end_date=str(rpt),
            fields="end_date,total_revenue,revenue,operate_profit,n_income,n_income_attr_p"
        )
        if df2 is not None and not df2.empty:
            parts.append("利润表摘要（近4期）：\n" + df2.head(4).to_string(index=False))
    except Exception as e:
        parts.append(f"利润表获取失败: {e}")

    return "\n\n".join(parts) if parts else "暂无财务数据（Tushare积分可能不足）"


@st.cache_data(ttl=300, show_spinner=False)
def get_news(ts_code: str, name: str) -> list:
    """个股相关新闻"""
    results = []
    try:
        # Tushare news by src (需要积分)
        df = pro.news(
            src="sina",
            start_date=(datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
            end_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            fields="datetime,title,content"
        )
        if df is not None and not df.empty:
            # Filter by name/code
            code6 = to_code6(ts_code)
            mask = df["title"].str.contains(name[:4], na=False) | \
                   df["title"].str.contains(code6, na=False)
            filtered = df[mask]
            if not filtered.empty:
                for _, row in filtered.head(10).iterrows():
                    results.append({
                        "发布时间": str(row.get("datetime", "")),
                        "新闻标题": str(row.get("title", "")),
                    })
    except Exception:
        pass

    # Fallback: 个股新闻接口
    if not results:
        try:
            df2 = pro.stk_news(ts_code=ts_code, fields="datetime,title")
            if df2 is not None and not df2.empty:
                for _, row in df2.head(12).iterrows():
                    results.append({
                        "发布时间": str(row.get("datetime", "")),
                        "新闻标题": str(row.get("title", "")),
                    })
        except Exception:
            pass

    return results


@st.cache_data(ttl=300, show_spinner=False)
def get_capital_flow(ts_code: str) -> str:
    """个股资金流向"""
    try:
        df = pro.moneyflow(
            ts_code=ts_code,
            start_date=ndays_ago(20),
            end_date=today(),
            fields="trade_date,buy_sm_amount,buy_md_amount,buy_lg_amount,buy_elg_amount,"
                   "sell_sm_amount,sell_md_amount,sell_lg_amount,sell_elg_amount,net_mf_amount"
        )
        if df is not None and not df.empty:
            df = df.sort_values("trade_date")
            df.columns = [c.replace("_amount","").replace("buy","买").replace("sell","卖")
                          .replace("sm","散户").replace("md","中户")
                          .replace("lg","大户").replace("elg","超大户")
                          .replace("net_mf","净流入") for c in df.columns]
            return df.tail(15).to_string(index=False)
    except Exception as e:
        return f"资金流向获取失败: {e}"
    return "暂无资金流向数据"


@st.cache_data(ttl=600, show_spinner=False)
def get_dragon_tiger(ts_code: str) -> str:
    """龙虎榜数据"""
    try:
        df = pro.top_list(
            trade_date=ndays_ago(30),
            ts_code=ts_code,
            fields="trade_date,name,close,pct_change,net_amount,net_rate,reason"
        )
        if df is not None and not df.empty:
            return df.head(10).to_string(index=False)
    except Exception:
        pass
    return "近30日无龙虎榜记录"


# ══════════════════════════════════════════════════════════════════════════════
# K-LINE CHART
# ══════════════════════════════════════════════════════════════════════════════

def render_kline(df: pd.DataFrame, name: str, ts_code: str) -> None:
    if df.empty:
        st.warning("⚠️ 暂无K线数据，请检查股票代码或网络连接")
        return

    df = df.copy()
    for p in [5, 20, 60]:
        df[f"MA{p}"] = df["收盘"].rolling(p).mean()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.02, row_heights=[0.72, 0.28],
    )

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df["日期"], open=df["开盘"], high=df["最高"],
        low=df["最低"], close=df["收盘"], name="K线",
        increasing=dict(line=dict(color="#22c55e", width=1.2), fillcolor="#22c55e"),
        decreasing=dict(line=dict(color="#ef4444", width=1.2), fillcolor="#ef4444"),
        whiskerwidth=0.5,
    ), row=1, col=1)

    ma_styles = {"MA5": ("#f97316", 1.6), "MA20": ("#6366f1", 1.6), "MA60": ("#a855f7", 1.6)}
    for ma, (clr, w) in ma_styles.items():
        fig.add_trace(go.Scatter(
            x=df["日期"], y=df[ma], name=ma,
            line=dict(color=clr, width=w), mode="lines", opacity=0.9,
        ), row=1, col=1)

    colors = ["#22c55e" if c >= o else "#ef4444"
              for c, o in zip(df["收盘"], df["开盘"])]
    fig.add_trace(go.Bar(
        x=df["日期"], y=df["成交量"], name="成交量",
        marker_color=colors, opacity=0.55,
    ), row=2, col=1)

    vol_ma = df["成交量"].rolling(5).mean()
    fig.add_trace(go.Scatter(
        x=df["日期"], y=vol_ma, name="量MA5",
        line=dict(color="#f97316", width=1.5), mode="lines", opacity=0.85,
    ), row=2, col=1)

    fig.update_layout(
        title=dict(
            text=f"<b>{name}（{to_code6(ts_code)}）</b>  日K线走势",
            font=dict(family="Nunito,sans-serif", size=14, color="#6b7280"),
        ),
        template="plotly_white",
        height=560,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#fafbff",
        paper_bgcolor="#ffffff",
        font=dict(family="Nunito,sans-serif", color="#6b7280", size=11),
        legend=dict(orientation="h", y=1.05, x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=50, b=15, l=10, r=10),
    )
    fig.update_xaxes(gridcolor="#e5e7eb", gridwidth=0.5, zeroline=False)
    fig.update_yaxes(gridcolor="#e5e7eb", gridwidth=0.5)

    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# AI ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def get_client() -> anthropic.Anthropic | None:
    key = st.session_state.get("api_key", "")
    return anthropic.Anthropic(api_key=key) if key else None


def call_claude(client: anthropic.Anthropic, prompt: str,
                system: str = "", max_tokens: int = 3200,
                use_search: bool = True) -> str:
    kwargs: dict = {
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if use_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    collected = ""
    try:
        for _ in range(10):
            resp = client.messages.create(**kwargs)
            for blk in resp.content:
                if blk.type == "text":
                    collected += blk.text
            if resp.stop_reason != "tool_use":
                break
            kwargs["messages"].append({"role": "assistant", "content": resp.content})
            tool_results = [
                {"type": "tool_result", "tool_use_id": blk.id,
                 "content": "请继续基于已有知识分析。"}
                for blk in resp.content if blk.type == "tool_use"
            ]
            kwargs["messages"].append({"role": "user", "content": tool_results})
    except Exception:
        kwargs.pop("tools", None)
        try:
            resp = client.messages.create(**kwargs)
            collected = "".join(
                b.text for b in resp.content if hasattr(b, "text") and b.type == "text"
            )
        except Exception as e:
            collected = f"⚠️ 分析生成失败：{e}"

    return collected or "⚠️ 未获得分析内容，请重试。"


def price_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "暂无K线数据"
    d = df.copy()
    for p in [5, 20, 60]:
        d[f"MA{p}"] = d["收盘"].rolling(p).mean()
    lt = d.iloc[-1]

    def pct(n):
        if len(d) <= n:
            return "N/A"
        return f"{(d.iloc[-1]['收盘'] / d.iloc[-n]['收盘'] - 1)*100:.2f}%"

    ma_arr = (
        "多头排列↑" if lt["MA5"] > lt["MA20"] > lt["MA60"]
        else "空头排列↓" if lt["MA5"] < lt["MA20"] < lt["MA60"]
        else "均线纠缠~"
    )

    lines = [
        f"最新收盘: {lt['收盘']:.2f}元",
        f"近期涨跌 — 5日:{pct(5)}  20日:{pct(20)}  60日:{pct(60)}",
        f"MA5={lt['MA5']:.2f}  MA20={lt['MA20']:.2f}  MA60={lt['MA60']:.2f}  → {ma_arr}",
        f"60日区间: 最高{d.tail(60)['最高'].max():.2f} / 最低{d.tail(60)['最低'].min():.2f}",
        "",
        "近15日 OHLCV：",
        d.tail(15)[["日期","开盘","最高","最低","收盘","成交量","涨跌幅"]].to_string(index=False),
    ]
    return "\n".join(lines)


# ── Module 1: 预期差 ──────────────────────────────────────────────────────────

def analyze_expectation_gap(client, name, ts_code, info, news) -> str:
    news_text = "\n".join(
        f"[{n.get('发布时间','')}] {n.get('新闻标题','')}"
        for n in news[:12]
    ) or "暂无最新新闻"
    info_str = json.dumps({k: v for k, v in info.items() if "err" not in k},
                          ensure_ascii=False)[:1400]
    prompt = f"""你是中国顶级买方研究院首席分析师，专精A股预期差挖掘与市场博弈分析。

## 分析标的
股票：{name}（{to_code6(ts_code)}）

## 公司基本信息
{info_str}

## 近期新闻动态
{news_text}

---
请结合上述信息及你掌握的市场知识，进行深度预期差分析（输出中文）：

### 一、当前核心炒作逻辑
详述当前市场炒作该股的核心叙事——是主题/概念驱动、业绩拐点、政策催化，还是资金博弈？逻辑强度与可持续性如何？

### 二、市场一致预期
目前市场（机构研报、卖方共识）对这只股的主流预期是什么？预期是否已经充分 price in？

### 三、预期差所在（核心价值）
**🟢 超预期方向（潜在正向惊喜）：**
- （列出2-3个可能超出市场预期的具体因素，说明逻辑）

**🔴 低预期风险（潜在负向惊喜）：**
- （列出1-2个可能不及预期的风险因素）

### 四、近期催化事件日历（未来1~3个月）
| 预计时间 | 催化事件 | 影响方向 | 重要性 |
|--------|---------|---------|------|

### 五、三情景分析
| 情景 | 触发条件 | 目标价区间 | 概率估计 |
|-----|---------|---------|--------|
| 🟢 乐观 | | | |
| 🟡 中性 | | | |
| 🔴 悲观 | | | |

### 六、综合结论
用2-3句话高度概括本次预期差分析的核心结论和操作启示。
"""
    return call_claude(client, prompt, max_tokens=3200)


# ── Module 2: 趋势 ────────────────────────────────────────────────────────────

def analyze_trend(client, name, ts_code, price_smry, capital, dragon) -> str:
    prompt = f"""你是资深A股技术分析师，深谙量价关系、主力行为与资金博弈。

## 分析标的：{name}（{to_code6(ts_code)}）

## K线及量价数据
{price_smry}

## 主力资金流向（近15日）
{capital[:700] if capital else '暂无'}

## 龙虎榜记录（近30日）
{dragon[:400] if dragon else '无记录'}

---
请进行专业的中短线技术与资金面综合分析（输出中文）：

### 一、K线形态识别
描述当前K线所处的技术形态，并标注关键支撑位与压力位。

### 二、均线系统解读
当前均线排列特征，各均线的支撑/压力意义，是否出现金叉/死叉？

### 三、量价关系分析
- 近期量能特征（缩量/放量/天量/地量）
- 量价配合健康度
- 主力建仓/出货的量价信号

### 四、资金动向研判
- 主力资金近期净流入/流出趋势
- 龙虎榜异动含义
- 筹码成本区估算

### 五、中短线趋势研判

**📌 短线展望（1-2周）：**
- 趋势：看多 / 看空 / 震荡
- 买入参考：___ 元  止损：___ 元  短线目标：___ 元

**📌 中线展望（1-3个月）：**
- 趋势方向及理由
- 目标区间：___ 元 ~ ___ 元  关键支撑：___ 元

### 六、历史相似走势参考案例（3个）
请给出3只历史上走势形态与{name}当前最相近的A股案例：

**【案例1】**
- 股票名称及代码：
- 相似时间背景：
- 相似走势特征：
- 后续走势结果：
- 对{name}的参考意义：

**【案例2】**（同格式）

**【案例3】**（同格式）
"""
    return call_claude(client, prompt, max_tokens=3500)


# ── Module 3: 基本面 ──────────────────────────────────────────────────────────

def analyze_fundamentals(client, name, ts_code, info, financial) -> str:
    info_str = json.dumps({k: v for k, v in info.items() if "err" not in k},
                          ensure_ascii=False)[:1000]
    prompt = f"""你是专业的A股基本面研究员，精通财务分析、公司质量评估与估值体系。

## 分析标的：{name}（{to_code6(ts_code)}）

## 基本信息
{info_str}

## 财务数据
{financial[:2200] if financial else '暂无'}

---
请进行全面基本面剖析，重点用于筛除垃圾公司（输出中文）：

### 一、财务健康体检

| 维度 | 评估内容 | 近期表现/趋势 | 评级（⭐1-5）|
|-----|---------|------------|------------|
| 成长性 | 营收/净利润CAGR | | |
| 盈利质量 | 净利率、现金含量、扣非 | | |
| 偿债安全 | 资负率、流动/速动比 | | |
| 资本效率 | ROE（近3年）、ROIC | | |
| 现金流 | 经营现金流 vs 净利润 | | |

**综合财务健康评分：X / 10**

### 二、盈利质量深析
- 利润"真实性"判断
- 财务水分风险点（商誉/应收/存货等）

### 三、核心竞争力评估
- 护城河类型及宽度
- 行业地位与竞争格局
- 管理层质量与大股东行为

### 四、估值分析
| 指标 | 当前值 | 历史分位 | 行业均值 | 判断 |
|-----|-------|--------|---------|-----|
| PE(TTM) | | | | |
| PB | | | | |
| PS | | | | |
| 股息率 | | | | |

**估值结论：** 低估 / 合理 / 偏贵 / 高估

### 五、风险预警雷达 🚨
1. **财务风险**
2. **股东风险**（减持/质押/解禁）
3. **经营风险**
4. **估值风险**

### 六、基本面裁决
**综合评分：X / 10**  
**能否通过筛选？** ✅ 通过 / ❌ 不通过 / ⚠️ 谨慎  
**核心理由：**
"""
    return call_claude(client, prompt, max_tokens=3200)


# ══════════════════════════════════════════════════════════════════════════════
# MoE DEBATE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

MOE_ROLES = [
    {
        "key": "trader", "css": "r-trader",
        "badge": "⚡ 短线游资 · 闪电刀",
        "system": (
            "你是A股短线游资操盘手，代号「闪电刀」，时间维度1-10个交易日。"
            "核心：题材热度、情绪共振、技术突破、龙头效应。判断直接，止损果断。"
            "语言风格：简练直白，带游资嗅觉，用「动力足不足」「有没有持续性」「跟不跟」等行话。"
        ),
    },
    {
        "key": "institution", "css": "r-inst",
        "badge": "🏛️ 中线机构 · 稳健先生",
        "system": (
            "你是头部公募基金资深基金经理，代号「稳健先生」，时间维度1-6个月。"
            "核心逻辑：基本面景气度+估值安全边际+政策配合。重视业绩拐点、回撤控制。"
            "语言风格：专业理性，逻辑严密，注重数据和逻辑链，善用研报式表述。"
        ),
    },
    {
        "key": "quant", "css": "r-quant",
        "badge": "🤖 量化资金 · Alpha机器",
        "system": (
            "你是A股量化多因子策略研究员，代号「Alpha机器」。"
            "基于数据和统计规律，关注动量/价值/质量/情绪/资金流因子。"
            "擅长量价背离、筹码统计、历史回测规律。语言精确，善用概率表述。"
        ),
    },
    {
        "key": "retail", "css": "r-retail",
        "badge": "👥 普通散户 · 韭菜代表（⚠️反向指标）",
        "system": (
            "你是典型A股散户，代号「韭菜代表」，你的观点是重要的反向参考指标！"
            "特征：追涨杀跌，被新闻和K线表象影响，高点最乐观，底部最恐慌。"
            "语言口语化，带散户特有的焦虑/贪婪/侥幸，爱用「感觉」「应该」「万一」。"
        ),
    },
]

CEO_SYSTEM = (
    "你是掌管300亿私募的顶级CEO，历经2008/2015/2018三次A股大崩盘，20年投资经验。"
    "深知散户情绪是最可靠的反向指标。善于综合各方观点，识别关键分歧变量。"
    "给出明确、可操作、附具体价格的最终裁决，不做模糊表述。"
)


def run_moe(client, name, ts_code, analyses: dict) -> None:
    code6 = to_code6(ts_code)
    summary = f"""=== 分析摘要：{name}（{code6}） ===

【预期差】
{analyses.get('expectation','')[:1000]}

【趋势】
{analyses.get('trend','')[:1000]}

【基本面】
{analyses.get('fundamentals','')[:1000]}""".strip()

    role_results: dict[str, str] = {}

    for role in MOE_ROLES:
        with st.spinner(f"{role['badge']} 正在发表观点..."):
            prompt = f"""辩论标的：{name}（{code6}）

背景摘要：
{summary[:2500]}

---
从你的角色视角给出明确判断，控制在220字以内。格式如下：

**核心判断：** 看多/看空/中性/观望

**主要依据（3条）：**
1.
2.
3.

**操作建议：** （具体操作+参考点位）

**最大风险：** （1个）

请保持角色特色和语言风格。"""
            text = call_claude(client, prompt, system=role["system"],
                               max_tokens=700, use_search=False)
            role_results[role["key"]] = text

        st.markdown(f"""<div class="role-card {role['css']}">
  <div class="role-badge">{role['badge']}</div>
  <div class="role-content">{text}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # CEO synthesis
    roles_text = "\n\n".join(
        f"【{r['badge']}】\n{role_results.get(r['key'],'')}" for r in MOE_ROLES
    )
    with st.spinner("👔 首席执行官 综合裁决中..."):
        ceo_prompt = f"""标的：{name}（{code6}）

四位专家观点：
{roles_text}

综合背景：
{summary[:1400]}

---
请给出最终操作裁决。**散户（韭菜代表）的观点是反向指标，请逆向思考。**

## 🎯 最终操作结论

**操作评级：** 强烈买入 / 买入 / 谨慎介入 / 持有观察 / 减持 / 回避

**裁决逻辑（3-4句）：**

**目标价体系：**
| 维度 | 价格 | 依据 |
|-----|-----|-----|
| 当前股价 | X.XX元 | — |
| 短线目标（1-2周） | | |
| 中线目标（1-3月） | | |
| 止损位 | | |

**仓位策略：**
- 建议仓位：X%（轻<30% / 中30-60% / 重>60%）
- 介入方式：

**核心逻辑（2条）：**
1.
2.

**核心风险（2条）：**
1.
2.

**策略有效期：** ___ 个交易日，若[具体条件]则策略失效。
"""
        ceo_text = call_claude(client, ceo_prompt, system=CEO_SYSTEM,
                               max_tokens=1600, use_search=False)

    st.markdown(f"""<div class="role-card r-ceo">
  <div class="role-badge">👔 首席执行官 · 最终裁决</div>
  <div class="role-content">{ceo_text}</div>
</div>""", unsafe_allow_html=True)

    st.session_state["moe_results"] = {
        "roles": role_results, "ceo": ceo_text, "done": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def show_results(client):
    r      = st.session_state.get("analyses", {})
    name   = st.session_state.get("stock_name", "")
    tscode = st.session_state.get("stock_code", "")
    df     = st.session_state.get("price_df", pd.DataFrame())

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 预期差分析",
        "📈 K线 & 趋势",
        "📋 基本面",
        "🎯 MoE 辩论裁决",
    ])

    with tab1:
        st.markdown(f'<div class="analysis-wrap">{r.get("expectation","⚠️ 暂无结果")}</div>',
                    unsafe_allow_html=True)

    with tab2:
        render_kline(df, name, tscode)
        st.markdown("---")
        st.markdown(f'<div class="analysis-wrap">{r.get("trend","⚠️ 暂无结果")}</div>',
                    unsafe_allow_html=True)

    with tab3:
        st.markdown(f'<div class="analysis-wrap">{r.get("fundamentals","⚠️ 暂无结果")}</div>',
                    unsafe_allow_html=True)

    with tab4:
        moe = st.session_state.get("moe_results", {})
        if moe.get("done"):
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
        else:
            st.info("💡 完成3项分析后，点击下方按钮启动四方辩论，获得带具体点位的操作结论。")
            st.caption("⚠️ 普通散户的观点将作为**反向指标**，首席执行官会逆向参考。")
            if not r:
                st.warning("请先点击「开始分析」完成股票分析。")
            elif client:
                if st.button("🎯 启动 MoE 辩论", type="primary"):
                    run_moe(client, name, tscode, r)
            else:
                st.warning("⚠️ 请先在左侧输入 Anthropic API Key。")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
<div class="app-header">
  <h1>📈 A股智能投研助手</h1>
  <p>预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE多角色辩论裁决</p>
</div>
""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔑 API 配置")
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            value=st.session_state.get("api_key", ""),
            placeholder="sk-ant-...",
            help="在 console.anthropic.com 获取",
        )
        if api_key:
            st.session_state["api_key"] = api_key
            st.success("✅ API Key 已设置")

        st.markdown("---")
        st.markdown("### 📖 使用方法")
        st.markdown("""
**① 输入 API Key（右上角设置）**

**② 输入股票代码或名称**
> 例：`600519` 或 `贵州茅台`

**③ 点击「开始分析」**
> 约 2-4 分钟完成分析

**④ 切换标签查看各模块**

**⑤ 「MoE辩论」标签**
> 点击启动，获取操作结论
""")

        st.markdown("---")
        st.markdown("""
<div class="disclaimer">
⚠️ <strong>免责声明</strong><br>
本工具仅供学习研究，不构成任何投资建议。A股市场风险较大，请独立判断，自行承担投资盈亏。
</div>
""", unsafe_allow_html=True)

    # ── Search Bar ────────────────────────────────────────────────────────────
    col_in, col_btn, col_clr = st.columns([5, 1.3, 0.8])
    with col_in:
        query = st.text_input(
            "搜索股票",
            label_visibility="collapsed",
            placeholder="🔍  输入股票代码（如 000858）或名称（如 五粮液）…",
            key="query_input",
        )
    with col_btn:
        start = st.button("🚀 开始分析", type="primary", use_container_width=True)
    with col_clr:
        if st.button("🗑 重置", use_container_width=True):
            for k in ["analyses", "stock_code", "stock_name",
                      "price_df", "stock_info", "moe_results"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Run ───────────────────────────────────────────────────────────────────
    if start and query:
        if not st.session_state.get("api_key"):
            st.error("⚠️ 请先在左侧边栏输入 Anthropic API Key！")
            st.stop()
        client = get_client()
        if not client:
            st.error("⚠️ API Key 无效，请检查后重试。")
            st.stop()

        st.session_state.pop("moe_results", None)

        with st.spinner("🔍 解析股票中..."):
            ts_code, name = resolve_stock(query)
        st.session_state["stock_code"] = ts_code
        st.session_state["stock_name"] = name

        with st.status(f"📥 正在获取 {name} 的市场数据...", expanded=True) as s:
            st.write("▶ 基本信息 & 估值指标...")
            info = get_basic_info(ts_code)
            st.session_state["stock_info"] = info

            st.write("▶ 日线K线数据（近140天）...")
            df = get_price_df(ts_code)
            st.session_state["price_df"] = df

            st.write("▶ 财务指标 & 利润表...")
            fin = get_financial(ts_code)

            st.write("▶ 新闻资讯...")
            news = get_news(ts_code, name)

            st.write("▶ 主力资金流向...")
            cap = get_capital_flow(ts_code)

            st.write("▶ 龙虎榜数据...")
            dragon = get_dragon_tiger(ts_code)

            s.update(label="✅ 数据获取完成！", state="complete")

        # Stock header
        st.markdown(f"### {name}　`{to_code6(ts_code)}`")
        cols = st.columns(6)
        metrics = [
            ("最新价",    info.get("最新价(元)", "—")),
            ("市盈率TTM", info.get("市盈率TTM", "—")),
            ("市净率PB",  info.get("市净率PB",  "—")),
            ("市销率PS",  info.get("市销率PS",  "—")),
            ("换手率",    info.get("换手率(%)", "—")),
            ("行业",      info.get("行业", "—")),
        ]
        for col, (label, val) in zip(cols, metrics):
            with col:
                st.metric(label, str(val)[:14])

        # AI analysis
        analyses: dict[str, str] = {}
        psmry = price_summary(df)

        with st.status("🤖 AI 深度分析中（约2-4分钟）...", expanded=True) as ai_s:
            st.write("1/3  🔍 预期差分析（搜索最新资讯）...")
            analyses["expectation"] = analyze_expectation_gap(
                client, name, ts_code, info, news)

            st.write("2/3  📈 趋势研判（分析量价与资金）...")
            analyses["trend"] = analyze_trend(
                client, name, ts_code, psmry, cap, dragon)

            st.write("3/3  📋 基本面剖析（解读财务数据）...")
            analyses["fundamentals"] = analyze_fundamentals(
                client, name, ts_code, info, fin)

            ai_s.update(label="✅ 三项分析完成！", state="complete")

        st.session_state["analyses"] = analyses
        st.success("✅ 分析完成！切换上方标签查看详情。进入「MoE辩论裁决」标签获取最终操作建议。")

    # ── Display ───────────────────────────────────────────────────────────────
    if st.session_state.get("analyses"):
        if not start:
            ts_code = st.session_state["stock_code"]
            name    = st.session_state["stock_name"]
            info    = st.session_state.get("stock_info", {})
            st.markdown(f"### {name}　`{to_code6(ts_code)}`")
        show_results(get_client())


if __name__ == "__main__":
    main()
