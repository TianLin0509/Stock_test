#!/usr/bin/env python3
"""
A股智能投研助手
A-Share Stock Intelligence Research Assistant
Powered by Claude AI + AKShare Market Data
"""

import streamlit as st
import anthropic
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json, os, re, time

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="A股智能投研助手",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS — Bloomberg Terminal × Nikkei Dark aesthetic
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans+SC:wght@300;400;500;600;700&family=Noto+Serif+SC:wght@400;700&display=swap');

:root {
  --bg-base:     #060810;
  --bg-card:     #0c0f1e;
  --bg-card2:    #111527;
  --border:      #1e2540;
  --border-hi:   #2d3460;
  --up:          #00d97e;
  --down:        #ff4757;
  --accent:      #4d9fff;
  --accent2:     #f7b731;
  --accent3:     #a55eea;
  --text-hi:     #e8ecf8;
  --text-mid:    #8892b0;
  --text-lo:     #4a5580;
  --glow-up:     0 0 20px rgba(0,217,126,0.15);
  --glow-dn:     0 0 20px rgba(255,71,87,0.15);
  --glow-ac:     0 0 20px rgba(77,159,255,0.15);
}

html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg-base) !important;
  font-family: 'IBM Plex Sans SC', 'PingFang SC', sans-serif;
  color: var(--text-hi);
}

[data-testid="stSidebar"] {
  background: var(--bg-card) !important;
  border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: var(--text-mid);
  font-size: 0.85rem;
}

/* Main header */
.terminal-header {
  background: linear-gradient(135deg, #060810 0%, #0c0f1e 60%, #0f1428 100%);
  border: 1px solid var(--border-hi);
  border-top: 2px solid var(--accent);
  border-radius: 4px 4px 0 0;
  padding: 1.6rem 2rem;
  margin-bottom: 1.2rem;
  position: relative;
  overflow: hidden;
}

.terminal-header::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent), var(--accent2), var(--accent3), transparent);
}

.terminal-header h1 {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.7rem;
  font-weight: 600;
  color: var(--text-hi);
  margin: 0;
  letter-spacing: 0.05em;
}

.terminal-header h1 span.accent { color: var(--accent); }
.terminal-header h1 span.up     { color: var(--up);     }

.terminal-header .subtitle {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  color: var(--text-lo);
  margin: 0.4rem 0 0 0;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

/* Metric cards */
.metric-row {
  display: flex;
  gap: 10px;
  margin: 1rem 0;
  flex-wrap: wrap;
}
.metric-card {
  background: var(--bg-card2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.7rem 1.1rem;
  min-width: 140px;
  flex: 1;
}
.metric-card .label {
  font-size: 0.68rem;
  color: var(--text-lo);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.metric-card .value {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-hi);
}
.metric-card .value.up   { color: var(--up);   }
.metric-card .value.down { color: var(--down); }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg-card) !important;
  border-radius: 3px;
  padding: 3px;
  gap: 2px;
  border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 2px !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.04em;
  color: var(--text-mid) !important;
  padding: 6px 16px !important;
}
.stTabs [aria-selected="true"] {
  background: var(--bg-card2) !important;
  color: var(--accent) !important;
  border-bottom: 2px solid var(--accent) !important;
}

/* Analysis content */
.analysis-block {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1.4rem 1.6rem;
  margin: 0.8rem 0;
  font-size: 0.92rem;
  line-height: 1.75;
  color: var(--text-hi);
}
.analysis-block h3 {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.85rem;
  color: var(--accent);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
}

/* MoE role blocks */
.role-block {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid;
  border-radius: 0 4px 4px 0;
  padding: 1.2rem 1.5rem;
  margin: 1rem 0;
  position: relative;
}
.role-block .role-badge {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 0.8rem;
  display: inline-block;
  padding: 2px 10px;
  border-radius: 2px;
}
.role-block .role-content {
  color: var(--text-hi);
  font-size: 0.9rem;
  line-height: 1.75;
  white-space: pre-wrap;
}

.role-trader      { border-left-color: #ff6b6b; }
.role-trader      .role-badge { background: rgba(255,107,107,0.12); color: #ff6b6b; }

.role-institution { border-left-color: var(--up); }
.role-institution .role-badge { background: rgba(0,217,126,0.1); color: var(--up); }

.role-quant       { border-left-color: var(--accent); }
.role-quant       .role-badge { background: rgba(77,159,255,0.1); color: var(--accent); }

.role-retail      { border-left-color: var(--accent2); }
.role-retail      .role-badge { background: rgba(247,183,49,0.1); color: var(--accent2); }

.role-ceo         {
  border-left-color: var(--accent3);
  background: linear-gradient(135deg, #0c0f1e, #12102a);
  border: 1px solid rgba(165,94,234,0.3);
  border-left: 3px solid var(--accent3);
  box-shadow: 0 0 30px rgba(165,94,234,0.08);
}
.role-ceo .role-badge { background: rgba(165,94,234,0.12); color: var(--accent3); }

/* Disclaimer badge */
.disclaimer {
  background: rgba(255,71,87,0.06);
  border: 1px solid rgba(255,71,87,0.2);
  border-radius: 3px;
  padding: 0.7rem 1rem;
  font-size: 0.78rem;
  color: var(--down);
  margin-top: 1rem;
}

/* Input styling */
.stTextInput input {
  background: var(--bg-card2) !important;
  border: 1px solid var(--border-hi) !important;
  border-radius: 3px !important;
  color: var(--text-hi) !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.95rem !important;
  padding: 0.55rem 1rem !important;
}
.stTextInput input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(77,159,255,0.15) !important;
}

/* Buttons */
.stButton button {
  border-radius: 3px !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-weight: 500 !important;
  letter-spacing: 0.05em !important;
  font-size: 0.85rem !important;
  transition: all 0.15s ease !important;
}
.stButton button[kind="primary"] {
  background: var(--accent) !important;
  border: none !important;
  color: #060810 !important;
}
.stButton button[kind="primary"]:hover {
  background: #6ab4ff !important;
  box-shadow: 0 0 15px rgba(77,159,255,0.3) !important;
}

/* Status/spinner */
[data-testid="stStatusWidget"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border-hi) !important;
  border-radius: 4px !important;
}

/* Streamlit metric */
[data-testid="metric-container"] {
  background: var(--bg-card2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 3px !important;
  padding: 0.7rem 1rem !important;
}
[data-testid="stMetricLabel"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.7rem !important;
  color: var(--text-lo) !important;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 1.1rem !important;
  color: var(--text-hi) !important;
}

/* Tables */
table { width: 100%; border-collapse: collapse; }
th {
  background: var(--bg-card2);
  color: var(--text-lo);
  font-size: 0.75rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-hi);
  text-align: left;
}
td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-hi);
  font-size: 0.88rem;
}
tr:hover td { background: var(--bg-card2); }

/* Sidebar */
[data-testid="stSidebar"] h3 {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.75rem;
  color: var(--accent);
  letter-spacing: 0.15em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.4rem;
  margin-bottom: 0.8rem;
}
[data-testid="stSidebar"] label {
  font-size: 0.8rem !important;
  color: var(--text-mid) !important;
  font-family: 'IBM Plex Mono', monospace !important;
}

/* Divider */
hr { border-color: var(--border) !important; margin: 1.2rem 0 !important; }

/* Info/warning */
[data-testid="stAlert"] {
  border-radius: 3px !important;
  border-left-width: 3px !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER — AKShare
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def load_stock_list() -> pd.DataFrame:
    try:
        import akshare as ak
        return ak.stock_info_a_code_name()
    except Exception:
        return pd.DataFrame(columns=["code", "name"])


def resolve_stock(query: str) -> tuple[str, str]:
    """Resolve stock code or name → (code, name)"""
    query = query.strip()
    if re.match(r"^\d{6}$", query):
        df = load_stock_list()
        m = df[df["code"] == query]
        return query, (m.iloc[0]["name"] if not m.empty else query)
    df = load_stock_list()
    if not df.empty:
        m = df[df["name"].str.contains(query, na=False)]
        if not m.empty:
            return m.iloc[0]["code"], m.iloc[0]["name"]
        m = df[df["code"].str.contains(query, na=False)]
        if not m.empty:
            return m.iloc[0]["code"], m.iloc[0]["name"]
    return query, query


@st.cache_data(ttl=300, show_spinner=False)
def get_basic_info(code: str) -> dict:
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        return {str(r.iloc[0]): str(r.iloc[1]) for _, r in df.iterrows()}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def get_price_df(code: str, days: int = 130) -> pd.DataFrame:
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        return ak.stock_zh_a_hist(symbol=code, period="daily",
                                  start_date=start, end_date=end, adjust="qfq")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_realtime(code: str) -> dict:
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        m = df[df["代码"] == code]
        return m.iloc[0].to_dict() if not m.empty else {}
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def get_financial(code: str) -> str:
    parts = []
    try:
        import akshare as ak
        # Annual financial abstract
        try:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
            if not df.empty:
                parts.append(f"年度财务摘要（近4年）：\n{df.head(4).to_string()}")
        except Exception:
            pass
        # Profit sheet
        try:
            df = ak.stock_profit_sheet_by_yearly_em(symbol=code)
            if not df.empty:
                parts.append(f"利润表（近年）：\n{df.iloc[:20, :5].to_string()}")
        except Exception:
            pass
    except Exception as e:
        parts.append(f"财务数据获取异常: {e}")
    return "\n\n".join(parts) if parts else "暂无财务数据"


@st.cache_data(ttl=300, show_spinner=False)
def get_news(code: str) -> list:
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        return df.head(15).to_dict("records") if not df.empty else []
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def get_capital_flow(code: str) -> str:
    try:
        import akshare as ak
        market = "sh" if code.startswith("6") else "sz"
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        return df.tail(20).to_string() if not df.empty else "暂无"
    except Exception:
        return "暂无资金流向数据"


# ══════════════════════════════════════════════════════════════════════════════
# K-LINE CHART
# ══════════════════════════════════════════════════════════════════════════════

def render_kline(df: pd.DataFrame, name: str, code: str) -> None:
    if df.empty:
        st.warning("⚠️ 暂无K线数据")
        return
    df = df.copy()
    for p in [5, 20, 60]:
        df[f"MA{p}"] = df["收盘"].rolling(p).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.025, row_heights=[0.72, 0.28])

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df["日期"], open=df["开盘"], high=df["最高"],
        low=df["最低"], close=df["收盘"], name="K线",
        increasing=dict(line=dict(color="#00d97e", width=1), fillcolor="#00d97e"),
        decreasing=dict(line=dict(color="#ff4757", width=1), fillcolor="#ff4757"),
        whiskerwidth=0.5
    ), row=1, col=1)

    # MAs
    ma_colors = {"MA5": "#ffd32a", "MA20": "#4d9fff", "MA60": "#a55eea"}
    for ma, color in ma_colors.items():
        fig.add_trace(go.Scatter(
            x=df["日期"], y=df[ma], name=ma,
            line=dict(color=color, width=1.4), opacity=0.9, mode="lines"
        ), row=1, col=1)

    # Volume bars
    colors = ["#00d97e" if c >= o else "#ff4757"
              for c, o in zip(df["收盘"], df["开盘"])]
    fig.add_trace(go.Bar(
        x=df["日期"], y=df["成交量"], name="成交量",
        marker_color=colors, opacity=0.6, showlegend=True
    ), row=2, col=1)

    # Volume MA5
    vol_ma = df["成交量"].rolling(5).mean()
    fig.add_trace(go.Scatter(
        x=df["日期"], y=vol_ma, name="量MA5",
        line=dict(color="#ffd32a", width=1), opacity=0.8, mode="lines"
    ), row=2, col=1)

    fig.update_layout(
        title=dict(text=f"<b>{name}（{code}）</b>  近期K线走势", 
                   font=dict(family="IBM Plex Mono", size=13, color="#8892b0")),
        template="plotly_dark",
        height=580,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#060810",
        paper_bgcolor="#0c0f1e",
        font=dict(family="IBM Plex Mono", color="#8892b0", size=11),
        legend=dict(orientation="h", y=1.04, x=0.01,
                    font=dict(size=10, color="#8892b0"),
                    bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=50, b=15, l=10, r=10),
        xaxis2=dict(showgrid=True, gridcolor="#1e2540", gridwidth=0.5),
        yaxis=dict(showgrid=True, gridcolor="#1e2540", gridwidth=0.5, tickfont=dict(size=10)),
        yaxis2=dict(showgrid=True, gridcolor="#1e2540", gridwidth=0.5, tickfont=dict(size=10)),
    )
    fig.update_xaxes(gridcolor="#1e2540", gridwidth=0.5, zeroline=False)

    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# AI ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def get_client() -> anthropic.Anthropic | None:
    key = st.session_state.get("api_key") or os.getenv("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=key) if key else None


def call_claude(client: anthropic.Anthropic, prompt: str,
                system: str = "", max_tokens: int = 3200,
                use_search: bool = True) -> str:
    """
    Claude API call with optional web search.
    Handles multi-turn tool use loop automatically.
    """
    kwargs: dict = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if use_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    collected_text = ""

    try:
        for _ in range(10):  # max tool-use loops
            resp = client.messages.create(**kwargs)

            for block in resp.content:
                if block.type == "text":
                    collected_text += block.text

            if resp.stop_reason != "tool_use":
                break

            # Append assistant turn + dummy tool results to continue
            kwargs["messages"].append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "请基于已有知识继续分析。"
                    })
            kwargs["messages"].append({"role": "user", "content": tool_results})

    except Exception:
        # Fallback: strip tools and retry once
        kwargs.pop("tools", None)
        try:
            resp = client.messages.create(**kwargs)
            collected_text = "".join(
                b.text for b in resp.content if hasattr(b, "text") and b.type == "text"
            )
        except Exception as e:
            collected_text = f"⚠️ 分析生成失败：{e}"

    return collected_text or "⚠️ 未获得分析内容，请重试。"


def price_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "暂无价格数据"
    d = df.copy()
    d["MA5"]  = d["收盘"].rolling(5).mean()
    d["MA20"] = d["收盘"].rolling(20).mean()
    d["MA60"] = d["收盘"].rolling(60).mean()
    latest = d.iloc[-1]

    def pct(n):
        return f"{(d.iloc[-1]['收盘'] / d.iloc[-n]['收盘'] - 1)*100:.2f}%" if len(d) > n else "N/A"

    lines = [
        f"最新价格: {latest['收盘']:.2f} 元",
        f"涨跌幅 - 5日: {pct(5)}  20日: {pct(20)}  60日: {pct(60)}",
        f"MA5={latest['MA5']:.2f}  MA20={latest['MA20']:.2f}  MA60={latest['MA60']:.2f}",
        f"60日最高: {d.tail(60)['最高'].max():.2f}  60日最低: {d.tail(60)['最低'].min():.2f}",
        f"均线排列: " + (
            "多头排列（上涨趋势）" if latest["MA5"] > latest["MA20"] > latest["MA60"]
            else "空头排列（下跌趋势）" if latest["MA5"] < latest["MA20"] < latest["MA60"]
            else "均线粘合/纠缠（震荡）"
        ),
        "",
        "近15日 OHLCV：",
        d.tail(15)[["日期", "开盘", "最高", "最低", "收盘", "成交量", "涨跌幅"]].to_string(index=False),
    ]
    return "\n".join(lines)


# ── Analysis Module 1 ─────────────────────────────────────────────────────────

def analyze_expectation_gap(client, name, code, info, news) -> str:
    news_text = "\n".join(
        f"[{n.get('发布时间','')}] {n.get('新闻标题','')}"
        for n in news[:12]
    )
    info_clean = {k: v for k, v in info.items() if k != "error"}
    prompt = f"""你是中国顶级买方研究院首席分析师，专精A股预期差挖掘与市场博弈分析。

## 分析标的
股票：{name}（{code}）

## 公司基本信息
{json.dumps(info_clean, ensure_ascii=False, indent=2)[:1400]}

## 近期新闻动态
{news_text}

---
请结合上述信息及你掌握的市场知识，进行深度预期差分析（输出中文）：

### 一、当前核心炒作逻辑
详述当前市场炒作该股的核心叙事——是主题/概念驱动、业绩拐点、政策催化，还是资金博弈？逻辑强度与可持续性如何？

### 二、市场一致预期
目前市场（机构研报、卖方共识）对这只股的主流预期是什么？预期是否已经充分price in？

### 三、预期差所在（核心价值）
**🟢 超预期方向（潜在正向惊喜）：**
- （列出2-3个可能超出市场预期的具体因素，说明逻辑）

**🔴 低预期风险（潜在负向惊喜）：**
- （列出1-2个可能不及预期的风险因素）

### 四、近期催化事件日历（未来1~3个月）
| 预计时间 | 催化事件 | 影响方向 | 重要性 |
|--------|---------|---------|------|
|  |  |  |  |

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


# ── Analysis Module 2 ─────────────────────────────────────────────────────────

def analyze_trend(client, name, code, price_smry, capital) -> str:
    prompt = f"""你是资深A股技术分析师，深谙量价关系、主力行为与资金博弈。

## 分析标的：{name}（{code}）

## K线及量价数据
{price_smry}

## 主力资金流向
{capital[:700] if capital else '暂无'}

---
请进行专业的中短线技术与资金面综合分析（输出中文）：

### 一、K线形态识别
描述当前K线所处的技术形态（底部/顶部/上升通道/旗形整理/头肩形等），并标注关键支撑位与压力位。

### 二、均线系统解读
当前均线排列特征 → 多头/空头/纠缠，各均线的支撑/压力意义，是否出现金叉/死叉？

### 三、量价关系分析
- 近期量能特征（缩量/放量/天量/地量）
- 量价配合是否健康（量价齐升/量缩价跌/量增价跌异常等）
- 是否有主力建仓/出货的量价信号？

### 四、资金动向研判
- 主力资金近期净流入/流出趋势
- 机构席位或游资异动迹象
- 筹码集中度及持仓成本区估算

### 五、中短线趋势研判

**📌 短线展望（未来1-2周）：**
- 趋势判断：看多 / 看空 / 震荡
- 关键点位：买入参考区间 ___ 元，止损 ___ 元，短线目标 ___ 元
- 操作策略：

**📌 中线展望（未来1-3个月）：**
- 趋势判断：
- 目标区间：___ 元 ~ ___ 元
- 关键支撑：___ 元
- 若跌破 ___ 元则趋势逆转需重新评估

### 六、历史相似走势参考案例
请基于你对A股历史的了解，找出3只在走势特征、形态阶段或行业背景上与{name}当前情况最相近的历史案例：

**【参考案例1】**
- 股票：[名称（代码）]
- 相似背景：（年份、处于什么阶段、什么走势形态）
- 相似特征：（与当前最相近的2-3个维度）
- 后续走势：（该股最终怎么走的？）
- 对{name}的参考意义：

**【参考案例2】**（同上格式）

**【参考案例3】**（同上格式）
"""
    return call_claude(client, prompt, max_tokens=3500)


# ── Analysis Module 3 ─────────────────────────────────────────────────────────

def analyze_fundamentals(client, name, code, info, financial) -> str:
    info_clean = {k: v for k, v in info.items() if k != "error"}
    prompt = f"""你是专业的A股基本面研究员，精通财务分析、公司质量评估与估值体系。

## 分析标的：{name}（{code}）

## 公司基本信息
{json.dumps(info_clean, ensure_ascii=False)[:1000]}

## 财务数据
{financial[:2200] if financial else '暂无'}

---
请进行全面的基本面剖析，重点用于筛除垃圾公司、识别优质标的（输出中文）：

### 一、财务健康体检

| 维度 | 评估内容 | 近期表现/趋势 | 评级（⭐1-5）|
|-----|---------|------------|------------|
| 成长性 | 营收/净利润3年CAGR | | |
| 盈利质量 | 净利率、现金含量、扣非净利 | | |
| 偿债安全 | 资产负债率、流动比、速动比 | | |
| 资本效率 | ROE（近3年）、ROIC | | |
| 现金流 | 经营现金流vs净利润 | | |

**综合财务健康评分：X / 10**

### 二、盈利质量深析
- 利润是否"真实"？有无财务水分迹象（商誉/应收/存货异常）？
- 扣非净利润与净利润的差距？
- 关注财务报表中的异常项目（如果有）

### 三、核心竞争力评估
- **护城河类型：** 品牌 / 专利技术 / 成本优势 / 网络效应 / 政策壁垒 / 规模效应
- **行业地位：** 行业排名、市占率变化、竞争格局
- **管理层：** 历史口碑、大股东行为、治理结构

### 四、估值分析
| 估值指标 | 当前值 | 历史均值分位 | 行业平均 | 判断 |
|--------|-------|-----------|---------|-----|
| PE（TTM）| | | | |
| PB | | | | |
| PS | | | | |
| 股息率 | | | | |

**估值结论：** 低估 / 合理 / 偏贵 / 高估

### 五、风险预警雷达 🚨
1. **财务风险**（造假风险 / 债务危机 / 商誉减值等）
2. **股东风险**（大股东减持计划 / 质押比例 / 解禁压力）
3. **经营风险**（行业竞争加剧 / 政策监管 / 技术路线迭代）
4. **估值风险**（是否存在明显泡沫）

### 六、基本面综合裁决
**综合评分：X / 10**
**投资评级：** 优质成长 / 稳健蓝筹 / 平庸一般 / 风险较高 / 建议回避

**能否通过基本面筛选？**
- ✅ 通过 / ❌ 不通过 / ⚠️ 谨慎通过
- 核心理由（1-2句话）：
"""
    return call_claude(client, prompt, max_tokens=3200)


# ══════════════════════════════════════════════════════════════════════════════
# MoE DEBATE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

MOE_ROLES = [
    {
        "key": "trader", "css": "role-trader",
        "badge": "⚡  短线游资  · 闪电刀",
        "system": (
            "你是A股市场资深短线游资操盘手，代号「闪电刀」。"
            "时间维度1-10个交易日。"
            "你的分析核心：题材热度、情绪共振、技术突破、板块轮动、龙头效应。"
            "你绝不废话，判断直接，止损果断。以趋势动量为王，高买高卖不手软。"
            "语言风格：简练直接，带游资特有的市场嗅觉，口头禅如「动力足不足」「有没有持续性」「跟不跟」。"
        ),
    },
    {
        "key": "institution", "css": "role-institution",
        "badge": "🏛️  中线机构  · 稳健先生",
        "system": (
            "你是国内头部公募基金的资深基金经理，代号「稳健先生」。"
            "时间维度1-6个月。"
            "核心逻辑：基本面景气度+估值安全边际+政策配合。"
            "重视业绩拐点识别、行业空间、仓位管理和回撤控制。"
            "语言风格：专业、理性、逻辑严密，善用研报式表述，注重数据和逻辑链。"
        ),
    },
    {
        "key": "quant", "css": "role-quant",
        "badge": "🤖  量化资金  · Alpha机器",
        "system": (
            "你是专业的A股量化多因子策略研究员，代号「Alpha机器」。"
            "你基于数据、统计规律和因子分析做判断，不做主观预测。"
            "关注因子：动量/价值/质量/情绪/资金流。"
            "擅长：量价背离、筹码分布统计、历史回测规律、相关性分析。"
            "语言风格：精确、量化，善用概率表述（「历史上X%的情况……」），警惕情绪化决策。"
        ),
    },
    {
        "key": "retail", "css": "role-retail",
        "badge": "👥  普通散户  · 韭菜代表（反向指标）",
        "system": (
            "你是典型的A股普通散户，代号「韭菜代表」。"
            "你代表市场大多数散户的情绪和思维方式。"
            "你的特征：追涨杀跌，容易被新闻和K线表象影响，在高点最乐观，在底部最恐慌。"
            "信息来源：股吧帖子、公众号、朋友推荐。"
            "注意：你的观点在本辩论中是重要的反向参考指标！"
            "语言风格：口语化，带有散户特有的焦虑、贪婪和侥幸心理，爱说「感觉」「应该」「万一」。"
        ),
    },
]

CEO_SYSTEM = (
    "你是掌管300亿元私募基金的顶级CEO，历经2008/2015/2018年三次A股大崩盘，投资经验超20年。"
    "你深知散户情绪是最可靠的反向指标。"
    "你善于综合各方观点，识别分歧中的关键变量，给出明确、可操作、附具体价格的最终裁决。"
    "你不做模糊表述，每个操作建议都必须有明确点位和止损。"
)


def run_moe(client, name, code, analyses: dict) -> None:
    """Run MoE debate: 4 roles → CEO synthesis. Display live."""
    summary = f"""
=== 综合分析摘要：{name}（{code}）===

【预期差分析】
{analyses.get('expectation','')[:1100]}

【趋势研判】
{analyses.get('trend','')[:1100]}

【基本面剖析】
{analyses.get('fundamentals','')[:1100]}
""".strip()

    role_results: dict[str, str] = {}

    for role in MOE_ROLES:
        badge = role["badge"]
        with st.spinner(f"{badge} 正在发表观点..."):
            prompt = f"""当前辩论标的：{name}（{code}）

综合分析背景（供参考）：
{summary[:2800]}

---
请从你的专业角色视角给出明确判断，控制在220字以内：

**核心判断：** [明确表态：看多/看空/中性/观望]

**主要依据（3条）：**
1.
2.
3.

**操作建议：** [具体操作+参考点位]

**最大风险：** [你最担心的1个风险]

请保持角色个性和语言特色。"""
            text = call_claude(client, prompt, system=role["system"], max_tokens=700, use_search=False)
            role_results[role["key"]] = text

        st.markdown(f"""
<div class="role-block {role['css']}">
  <div class="role-badge">{badge}</div>
  <div class="role-content">{text}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")

    # CEO synthesis
    roles_text = "\n\n".join(
        f"【{r['badge']}】\n{role_results.get(r['key'],'')}"
        for r in MOE_ROLES
    )
    with st.spinner("👔 首席执行官 正在综合裁决..."):
        ceo_prompt = f"""
标的：{name}（{code}）

四位专家观点：
{roles_text}

综合分析背景：
{summary[:1500]}

---
请给出你作为首席执行官的最终操作裁决。

特别提醒：散户（韭菜代表）的观点通常是反向指标，需逆向思考。

---
## 🎯 最终操作结论

**操作评级：**  [ 强烈买入 / 买入 / 谨慎介入 / 持有观察 / 减持 / 回避 ]

**裁决逻辑（3-4句话）：**
综合游资的情绪嗅觉、机构的中线研判、量化的数据信号，并逆向参考散户情绪，本次裁决认为……

**目标价体系：**
| 维度 | 价格区间 | 依据 |
|-----|--------|-----|
| 当前股价 | X.XX 元 | — |
| 短线目标（1-2周） | X.XX 元 | |
| 中线目标（1-3月） | X.XX 元 | |
| 止损位 | X.XX 元（若跌破则清仓） | |
| 预期最大收益 | +X% | |

**仓位策略：**
- 建议仓位：X%（轻 < 30% / 中 30-60% / 重 > 60%）
- 介入方式：（一次性 / 分X批，参考价格）

**核心做多/做空逻辑（最重要的2条）：**
1.
2.

**需重点监控的风险（2条）：**
1.
2.

**操作时效声明：** 以上结论有效期 ___ 个交易日，若 [具体条件] 发生则策略失效，需重新评估。
"""
        ceo_text = call_claude(client, ceo_prompt, system=CEO_SYSTEM, max_tokens=1600, use_search=False)

    st.markdown(f"""
<div class="role-block role-ceo">
  <div class="role-badge">👔  首席执行官  · 综合裁决</div>
  <div class="role-content">{ceo_text}</div>
</div>
""", unsafe_allow_html=True)

    st.session_state["moe_results"] = {
        "roles": role_results,
        "ceo": ceo_text,
        "done": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def show_results(client):
    r = st.session_state.get("analyses", {})
    name = st.session_state.get("stock_name", "")
    code = st.session_state.get("stock_code", "")
    df   = st.session_state.get("price_df", pd.DataFrame())

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍  预期差分析",
        "📈  K线 & 趋势研判",
        "📋  基本面剖析",
        "🎯  MoE 辩论博弈",
    ])

    with tab1:
        st.markdown(r.get("expectation", "⚠️ 暂无分析结果"))

    with tab2:
        render_kline(df, name, code)
        st.markdown("---")
        st.markdown(r.get("trend", "⚠️ 暂无分析结果"))

    with tab3:
        st.markdown(r.get("fundamentals", "⚠️ 暂无分析结果"))

    with tab4:
        moe = st.session_state.get("moe_results", {})
        if moe.get("done"):
            # Replay stored MoE results
            for role in MOE_ROLES:
                text = moe["roles"].get(role["key"], "")
                st.markdown(f"""
<div class="role-block {role['css']}">
  <div class="role-badge">{role['badge']}</div>
  <div class="role-content">{text}</div>
</div>
""", unsafe_allow_html=True)
            st.markdown("---")
            st.markdown(f"""
<div class="role-block role-ceo">
  <div class="role-badge">👔  首席执行官  · 综合裁决</div>
  <div class="role-content">{moe['ceo']}</div>
</div>
""", unsafe_allow_html=True)
        else:
            # First-time MoE trigger
            st.markdown("""
> 四位不同风格的投资角色从各自视角辩论，最终由**首席执行官**综合裁决，给出操作结论与目标价。
>
> ⚠️ **注意：「普通散户」的观点是反向指标，首席执行官将逆向参考。**
""")
            if not r:
                st.warning("请先完成股票分析（点击「开始分析」），再运行 MoE 辩论。")
            elif client:
                if st.button("🎯  启动 MoE 辩论博弈", type="primary", use_container_width=False):
                    st.markdown("---")
                    run_moe(client, name, code, r)
            else:
                st.error("请先输入有效的 Anthropic API Key。")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
<div class="terminal-header">
  <h1>
    <span class="accent">📈</span>
    A股智能投研助手
    <span style="font-size:0.6em; color:#4a5580; margin-left:1em;">ALPHA v1.0</span>
  </h1>
  <p class="subtitle">
    预期差挖掘 · K线趋势研判 · 基本面剖析 · MoE 多角色辩论 · 操作结论
  </p>
</div>
""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ API 配置")
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            value=st.session_state.get("api_key", os.getenv("ANTHROPIC_API_KEY", "")),
            placeholder="sk-ant-...",
            help="在 console.anthropic.com 获取 API Key",
        )
        if api_key:
            st.session_state["api_key"] = api_key

        st.markdown("---")
        st.markdown("### 📖 使用说明")
        st.markdown("""
**① 输入 Anthropic API Key**

**② 输入股票代码或名称**
- 6位代码：`600519`
- 中文名：`贵州茅台`、`宁德时代`

**③ 点击「开始分析」**
约 2-4 分钟完成3项分析

**④ 切换标签查看结果**

**⑤ 进入「MoE辩论」标签**
点击启动辩论，再等 1-2 分钟
获得最终操作结论
""")
        st.markdown("---")
        st.markdown("### ⚠️ 免责声明")
        st.markdown("""
<div class="disclaimer">
本工具仅供学习研究参考，不构成任何投资建议。<br>
A股市场风险极大，请自行判断，自行承担投资损益。
</div>
""", unsafe_allow_html=True)

    # ── Input Row ─────────────────────────────────────────────────────────────
    col_in, col_btn, col_clr = st.columns([5, 1.2, 0.8])
    with col_in:
        query = st.text_input(
            "stock_input",
            label_visibility="collapsed",
            placeholder="输入股票代码（如 000858）或名称（如 五粮液 / 宁德时代）…",
            key="query_input",
        )
    with col_btn:
        start = st.button("🚀  开始分析", type="primary", use_container_width=True)
    with col_clr:
        if st.button("🗑  重置", use_container_width=True):
            for k in ["analyses", "stock_code", "stock_name", "price_df",
                      "stock_info", "moe_results"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Run Analysis ──────────────────────────────────────────────────────────
    if start and query:
        if not st.session_state.get("api_key"):
            st.error("⚠️ 请先在左侧边栏输入 Anthropic API Key！")
            st.stop()

        client = get_client()
        if not client:
            st.error("⚠️ API Key 无效，请检查后重试。")
            st.stop()

        # Clear previous MoE
        st.session_state.pop("moe_results", None)

        # Resolve stock
        with st.spinner("🔍 正在识别股票..."):
            code, name = resolve_stock(query)
        st.session_state["stock_code"] = code
        st.session_state["stock_name"] = name

        # Fetch data
        with st.status("📥 正在获取市场数据...", expanded=True) as s:
            st.write("▶ 股票基本信息...")
            info = get_basic_info(code)
            st.session_state["stock_info"] = info

            st.write("▶ K线历史数据...")
            df = get_price_df(code)
            st.session_state["price_df"] = df

            st.write("▶ 财务数据...")
            fin = get_financial(code)

            st.write("▶ 新闻资讯...")
            news = get_news(code)

            st.write("▶ 资金流向...")
            cap = get_capital_flow(code)

            s.update(label="✅ 数据获取完成", state="complete")

        # Stock header metrics
        st.markdown(f"### {name}（{code}）")
        rt = get_realtime(code)
        if rt:
            change = rt.get("涨跌幅", 0)
            try:
                change_f = float(str(change).replace("%", ""))
                change_cls = "up" if change_f >= 0 else "down"
                change_str = f"{'+' if change_f >= 0 else ''}{change_f:.2f}%"
            except Exception:
                change_cls = ""; change_str = str(change)

            cols = st.columns(6)
            metrics = [
                ("最新价 (元)",   f"¥ {rt.get('最新价','N/A')}",    ""),
                ("今日涨跌幅",    change_str,                        change_cls),
                ("总市值",        rt.get("总市值", info.get("总市值","N/A")), ""),
                ("市盈率(动)",    rt.get("市盈率-动态", info.get("市盈率(动)", "N/A")), ""),
                ("市净率",        rt.get("市净率", info.get("市净率","N/A")), ""),
                ("所属板块",      info.get("所属板块", info.get("板块","N/A")), ""),
            ]
            for col, (label, val, cls) in zip(cols, metrics):
                with col:
                    st.metric(label, str(val)[:14])

        # Run 3 AI analyses
        analyses: dict[str, str] = {}
        psmry = price_summary(df)

        with st.status("🤖 AI 深度分析中...", expanded=True) as ai_s:
            st.write("1 / 3  🔍 预期差分析...")
            analyses["expectation"] = analyze_expectation_gap(client, name, code, info, news)

            st.write("2 / 3  📈 趋势研判...")
            analyses["trend"] = analyze_trend(client, name, code, psmry, cap)

            st.write("3 / 3  📋 基本面剖析...")
            analyses["fundamentals"] = analyze_fundamentals(client, name, code, info, fin)

            ai_s.update(label="✅ 分析完成！切换标签查看详情", state="complete")

        st.session_state["analyses"] = analyses
        st.success("✅ 分析完成！切换上方标签查看各项分析。第4个标签可启动 **MoE辩论博弈** 获取操作结论。")

    # ── Show Results ──────────────────────────────────────────────────────────
    if st.session_state.get("analyses"):
        if not start:  # if fresh analysis, header already shown above
            code = st.session_state["stock_code"]
            name = st.session_state["stock_name"]
            info = st.session_state.get("stock_info", {})
            st.markdown(f"### {name}（{code}）")

        client = get_client()
        show_results(client)


if __name__ == "__main__":
    main()
