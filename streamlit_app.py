#!/usr/bin/env python3
"""
📈 A股智能投研助手 v3
Multi-Model (Qwen / 智谱 / 豆包 / DeepSeek) + Tushare
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json, re
from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError

# ══════════════════════════════════════════════════════════════════════════════
# TUSHARE INIT
# ══════════════════════════════════════════════════════════════════════════════
import tushare as ts

TUSHARE_TOKEN = "96e4ecf7246cddb2f781283bb1bbf7e45c6277a0e818a6ab1b4dcc31ea84"
TUSHARE_URL   = "http://lianghua.nanyangqiankun.top"

def init_tushare():
    try:
        ts.set_token(TUSHARE_TOKEN)
        p = ts.pro_api()
        p._DataApi__http_url = TUSHARE_URL
        # Quick health check
        test = p.trade_cal(exchange="SSE", start_date="20240101", end_date="20240103")
        if test is None:
            return None, "Tushare 接口返回空，请检查 Token 或网络"
        return p, None
    except Exception as e:
        return None, f"Tushare 初始化失败：{e}"

# Initialize at startup
_pro, _ts_err = init_tushare()

# ══════════════════════════════════════════════════════════════════════════════
# MODEL CONFIGS — 硬编码，无需用户输入
# ══════════════════════════════════════════════════════════════════════════════
MODEL_CONFIGS = {
    "🟠 Qwen · 通义千问": {
        "api_key":        "sk-0c6c7fdf79984ae68e83f03230a95b19",
        "base_url":       "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model":          "qwen-plus-latest",       # 最新 Qwen Plus
        "supports_search": True,                    # 通过 enable_search 开启联网
        "provider":       "qwen",
        "note":           "Qwen Plus · 联网搜索已开启",
    },
    "🔵 智谱 · GLM": {
        "api_key":        "",                        # 待补充
        "base_url":       "https://open.bigmodel.cn/api/paas/v4/",
        "model":          "glm-4-plus",
        "supports_search": True,
        "provider":       "zhipu",
        "note":           "GLM-4-Plus · 联网搜索",
    },
    "🟣 豆包 · 字节跳动": {
        "api_key":        "",                        # 待补充
        "base_url":       "https://ark.cn-beijing.volces.com/api/v3",
        "model":          "doubao-pro-32k",
        "supports_search": False,
        "provider":       "doubao",
        "note":           "Doubao Pro 32K",
    },
    "⚫ DeepSeek": {
        "api_key":        "",                        # 待补充
        "base_url":       "https://api.deepseek.com",
        "model":          "deepseek-chat",
        "supports_search": False,
        "provider":       "deepseek",
        "note":           "DeepSeek-V3",
    },
}

MODEL_NAMES = list(MODEL_CONFIGS.keys())

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
# CSS — 浅色可爱风
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
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text-mid) !important; }
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong { color: var(--blue) !important; }

/* App header */
.app-header {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
  border-radius: var(--radius);
  padding: 1.6rem 2rem;
  margin-bottom: 1.2rem;
  position: relative; overflow: hidden;
  box-shadow: 0 8px 32px rgba(99,102,241,0.25);
}
.app-header::before {
  content: '📊 📈 💹 📉 🏦';
  position: absolute; top: 12px; right: 8px;
  font-size: 1.4rem; opacity: 0.13;
  white-space: nowrap; letter-spacing: 0.6em;
}
.app-header h1 {
  font-family: 'Nunito', sans-serif;
  font-size: 1.9rem; font-weight: 800;
  color: #fff; margin: 0;
  text-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.app-header p {
  color: rgba(255,255,255,0.82);
  font-size: 0.86rem; margin: 0.35rem 0 0;
  font-weight: 500;
}

/* Model status badge */
.model-badge {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--bg-soft);
  border: 1.5px solid var(--border);
  border-radius: 50px;
  padding: 4px 14px;
  font-size: 0.82rem; font-weight: 600;
  color: var(--blue);
  margin-bottom: 1rem;
}
.model-badge.ok   { background: #f0fdf4; border-color: #86efac; color: #16a34a; }
.model-badge.warn { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
.model-badge.err  { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }

/* Status banner */
.status-banner {
  border-radius: var(--radius-sm);
  padding: 0.75rem 1.1rem;
  margin: 0.5rem 0;
  font-size: 0.86rem;
  line-height: 1.6;
  display: flex; align-items: flex-start; gap: 10px;
}
.status-banner.info    { background: var(--blue-lt);   border: 1px solid #c7d2fe; color: #3730a3; }
.status-banner.warn    { background: #fff7ed;           border: 1px solid #fed7aa; color: #92400e; }
.status-banner.error   { background: #fef2f2;           border: 1px solid #fca5a5; color: #991b1b; }
.status-banner.success { background: #f0fdf4;           border: 1px solid #86efac; color: #14532d; }

/* Cards */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.4rem 1.6rem;
  margin: 0.7rem 0;
  box-shadow: var(--shadow);
}

/* Tabs */
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
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  color: #fff !important;
  box-shadow: 0 2px 10px rgba(99,102,241,0.3) !important;
}

/* MoE role cards */
.role-card {
  border-radius: var(--radius); padding: 1.3rem 1.5rem;
  margin: 0.9rem 0; border: 1px solid; position: relative;
}
.role-badge {
  font-family: 'Nunito', sans-serif; font-size: 0.8rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 12px; border-radius: 50px;
  display: inline-block; margin-bottom: 0.8rem;
}
.role-content { font-size: 0.9rem; line-height: 1.8; white-space: pre-wrap; color: var(--text); }

.r-trader  { background: #fff5f5; border-color: #fca5a5; }
.r-trader  .role-badge { background: #fee2e2; color: #dc2626; }
.r-inst    { background: #f0fdf4; border-color: #86efac; }
.r-inst    .role-badge { background: #dcfce7; color: #16a34a; }
.r-quant   { background: var(--blue-lt); border-color: #c7d2fe; }
.r-quant   .role-badge { background: #e0e7ff; color: var(--blue); }
.r-retail  { background: var(--orange-lt); border-color: #fed7aa; }
.r-retail  .role-badge { background: #ffedd5; color: var(--orange); }
.r-ceo {
  background: linear-gradient(135deg, var(--purple-lt) 0%, var(--pink-lt) 100%);
  border-color: #d8b4fe;
  box-shadow: 0 4px 24px rgba(168,85,247,0.12);
}
.r-ceo .role-badge {
  background: linear-gradient(135deg, var(--purple), var(--pink));
  color: #fff; box-shadow: 0 2px 8px rgba(168,85,247,0.3);
}

/* Analysis wrap */
.analysis-wrap {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.6rem 1.8rem;
  box-shadow: var(--shadow); line-height: 1.8; font-size: 0.92rem;
}

/* Buttons */
.stButton button {
  border-radius: 50px !important;
  font-family: 'Nunito', sans-serif !important;
  font-weight: 700 !important; font-size: 0.88rem !important;
  padding: 0.5rem 1.4rem !important;
}
.stButton button[kind="primary"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  border: none !important; color: #fff !important;
  box-shadow: 0 4px 14px rgba(99,102,241,0.3) !important;
}
.stButton button[kind="primary"]:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4) !important;
}

/* Input */
.stTextInput input {
  border-radius: 50px !important;
  border: 2px solid var(--border) !important;
  background: var(--bg-card) !important;
  padding: 0.55rem 1.2rem !important;
  font-size: 0.95rem !important;
}
.stTextInput input:focus {
  border-color: var(--blue) !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
}

/* Select box */
.stSelectbox [data-baseweb="select"] > div {
  border-radius: var(--radius-sm) !important;
  border-color: var(--border) !important;
  background: var(--bg-card) !important;
}

/* Metrics */
[data-testid="metric-container"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  padding: 0.9rem 1rem !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.72rem !important; color: var(--text-lo) !important;
  font-weight: 600 !important; letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Nunito', sans-serif !important;
  font-size: 1.15rem !important; font-weight: 800 !important;
  color: var(--text) !important;
}
/* Disclaimer */
.disclaimer {
  background: #fff7ed; border: 1px solid #fed7aa;
  border-radius: var(--radius-sm); padding: 0.7rem 1rem;
  font-size: 0.78rem; color: #c2410c; margin-top: 0.8rem; line-height: 1.6;
}
hr { border-color: var(--border) !important; margin: 1rem 0 !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# AI CLIENT — OpenAI-compatible, multi-provider
# ══════════════════════════════════════════════════════════════════════════════

def get_ai_client(model_name: str) -> tuple[OpenAI | None, dict | None, str | None]:
    """返回 (client, config, error_msg)"""
    cfg = MODEL_CONFIGS.get(model_name)
    if not cfg:
        return None, None, "未知模型配置"
    if not cfg["api_key"]:
        return None, cfg, f"「{model_name}」的 API Key 尚未配置，请在 app.py 中填写"
    try:
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        return client, cfg, None
    except Exception as e:
        return None, cfg, str(e)


def call_ai(client: OpenAI, cfg: dict, prompt: str,
            system: str = "", max_tokens: int = 3200) -> tuple[str, str | None]:
    """
    调用 AI 模型。返回 (text, error_msg)。
    Qwen 等支持联网的模型会自动开启 enable_search。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    extra: dict = {}
    if cfg.get("supports_search") and cfg.get("provider") == "qwen":
        extra["extra_body"] = {"enable_search": True}
    elif cfg.get("supports_search") and cfg.get("provider") == "zhipu":
        extra["tools"] = [{"type": "web_search", "web_search": {"enable": True}}]

    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            max_tokens=max_tokens,
            **extra,
        )
        text = resp.choices[0].message.content or ""
        return text, None

    except AuthenticationError:
        return "", "API Key 认证失败，请检查密钥是否正确或已过期"
    except RateLimitError:
        return "", "调用频率或额度超限，请稍后重试或切换其他模型"
    except APIConnectionError as e:
        return "", f"网络连接失败：{e}"
    except Exception as e:
        err = str(e)
        # 常见错误友化
        if "invalid_api_key" in err.lower() or "401" in err:
            return "", "API Key 无效，请切换其他模型或检查密钥"
        if "quota" in err.lower() or "insufficient" in err.lower():
            return "", "账户余额不足，请充值或切换模型"
        if "model_not_found" in err.lower() or "does not exist" in err.lower():
            return "", f"模型不存在（{cfg['model']}），请联系开发者更新模型名称"
        return "", f"AI 调用异常：{err[:120]}"


# ══════════════════════════════════════════════════════════════════════════════
# TUSHARE DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def ts_ok() -> bool:
    return _pro is not None


def get_pro():
    if _pro is None:
        st.error(f"⚠️ Tushare 不可用：{_ts_err}")
    return _pro


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list() -> tuple[pd.DataFrame, str | None]:
    pro = get_pro()
    if pro is None:
        return pd.DataFrame(), _ts_err
    try:
        df = pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,industry,area,market"
        )
        return (df if df is not None else pd.DataFrame()), None
    except Exception as e:
        return pd.DataFrame(), str(e)


def resolve_stock(query: str) -> tuple[str, str, str | None]:
    """→ (ts_code, name, err)"""
    query = query.strip()
    df, err = load_stock_list()

    if err:
        code6 = re.sub(r"\D", "", query) or "000001"
        ts_code = to_ts_code(code6)
        return ts_code, query, f"股票列表获取失败（{err}），已按代码直接查询"

    if not df.empty:
        if re.match(r"^\d{6}$", query):
            m = df[df["symbol"] == query]
            if not m.empty:
                return m.iloc[0]["ts_code"], m.iloc[0]["name"], None
            return to_ts_code(query), query, None

        m = df[df["name"].str.contains(query, na=False)]
        if not m.empty:
            return m.iloc[0]["ts_code"], m.iloc[0]["name"], None

        m = df[df["symbol"].str.contains(query, na=False)]
        if not m.empty:
            return m.iloc[0]["ts_code"], m.iloc[0]["name"], None

    code6 = re.sub(r"\D", "", query) or "000001"
    return to_ts_code(code6), query, None


def to_ts_code(code6: str) -> str:
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


@st.cache_data(ttl=600, show_spinner=False)
def get_basic_info(ts_code: str) -> tuple[dict, str | None]:
    pro = get_pro()
    if pro is None:
        return {}, _ts_err
    result = {}
    err_msgs = []

    df_list, _ = load_stock_list()
    if not df_list.empty:
        m = df_list[df_list["ts_code"] == ts_code]
        if not m.empty:
            row = m.iloc[0]
            result.update({"名称": row.get("name",""), "行业": row.get("industry",""),
                           "地区": row.get("area",""), "市场": row.get("market","")})
    try:
        df_db = pro.daily_basic(
            ts_code=ts_code, start_date=ndays_ago(10), end_date=today(),
            fields="ts_code,trade_date,close,pe_ttm,pb,ps_ttm,total_mv,turnover_rate,volume_ratio"
        )
        if df_db is not None and not df_db.empty:
            row = df_db.iloc[0]
            mv = row.get("total_mv")
            result.update({
                "最新价(元)":    str(row.get("close","N/A")),
                "市盈率TTM":     str(row.get("pe_ttm","N/A")),
                "市净率PB":      str(row.get("pb","N/A")),
                "市销率PS":      str(row.get("ps_ttm","N/A")),
                "总市值(万元)":  f"{float(mv):,.0f}" if mv else "N/A",
                "换手率(%)":     str(row.get("turnover_rate","N/A")),
                "量比":          str(row.get("volume_ratio","N/A")),
            })
    except Exception as e:
        err_msgs.append(f"估值数据：{e}")

    return result, ("; ".join(err_msgs) if err_msgs else None)


@st.cache_data(ttl=300, show_spinner=False)
def get_price_df(ts_code: str, days: int = 140) -> tuple[pd.DataFrame, str | None]:
    pro = get_pro()
    if pro is None:
        return pd.DataFrame(), _ts_err
    try:
        df = pro.daily(ts_code=ts_code, start_date=ndays_ago(days), end_date=today())
        if df is None or df.empty:
            return pd.DataFrame(), "未获取到K线数据，可能是停牌或代码有误"
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df.rename(columns={
            "trade_date": "日期", "open": "开盘", "high": "最高",
            "low": "最低", "close": "收盘", "vol": "成交量",
            "pct_chg": "涨跌幅", "amount": "成交额",
        })
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"K线数据获取失败：{e}"


@st.cache_data(ttl=600, show_spinner=False)
def get_financial(ts_code: str) -> tuple[str, str | None]:
    pro = get_pro()
    if pro is None:
        return "", _ts_err
    parts, errs = [], []
    try:
        df = pro.fina_indicator(
            ts_code=ts_code,
            fields="end_date,roe,roa,grossprofit_margin,netprofit_margin,"
                   "debt_to_assets,current_ratio,quick_ratio,revenue_yoy,netprofit_yoy,basic_eps"
        )
        if df is not None and not df.empty:
            parts.append("核心财务指标（近5期）：\n" + df.head(5).to_string(index=False))
    except Exception as e:
        errs.append(f"财务指标：{e}")
    try:
        rpt = str((datetime.now().year - 1) * 10000 + 1231)
        df2 = pro.income(
            ts_code=ts_code, start_date=str(int(rpt)-30000), end_date=rpt,
            fields="end_date,total_revenue,operate_profit,n_income,n_income_attr_p"
        )
        if df2 is not None and not df2.empty:
            parts.append("利润表摘要（近4期）：\n" + df2.head(4).to_string(index=False))
    except Exception as e:
        errs.append(f"利润表：{e}")

    return ("\n\n".join(parts) if parts else "暂无财务数据"), \
           ("; ".join(errs) if errs else None)


@st.cache_data(ttl=300, show_spinner=False)
def get_news(ts_code: str, name: str) -> tuple[list, str | None]:
    pro = get_pro()
    if pro is None:
        return [], _ts_err
    results = []
    try:
        df = pro.stk_news(ts_code=ts_code, fields="datetime,title")
        if df is not None and not df.empty:
            for _, row in df.head(12).iterrows():
                results.append({"发布时间": str(row.get("datetime","")),
                                 "新闻标题": str(row.get("title",""))})
            return results, None
    except Exception:
        pass
    try:
        code6 = to_code6(ts_code)
        df2 = pro.news(
            src="sina",
            start_date=(datetime.now()-timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
            end_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            fields="datetime,title"
        )
        if df2 is not None and not df2.empty:
            mask = df2["title"].str.contains(name[:4], na=False) | \
                   df2["title"].str.contains(code6, na=False)
            for _, row in df2[mask].head(10).iterrows():
                results.append({"发布时间": str(row.get("datetime","")),
                                 "新闻标题": str(row.get("title",""))})
    except Exception as e:
        return results, f"新闻获取受限（{e}），AI将依赖内部知识分析"

    return results, None


@st.cache_data(ttl=300, show_spinner=False)
def get_capital_flow(ts_code: str) -> tuple[str, str | None]:
    pro = get_pro()
    if pro is None:
        return "", _ts_err
    try:
        df = pro.moneyflow(
            ts_code=ts_code, start_date=ndays_ago(20), end_date=today(),
            fields="trade_date,buy_sm_amount,buy_md_amount,buy_lg_amount,"
                   "buy_elg_amount,sell_sm_amount,sell_md_amount,sell_lg_amount,"
                   "sell_elg_amount,net_mf_amount"
        )
        if df is not None and not df.empty:
            return df.sort_values("trade_date").tail(15).to_string(index=False), None
        return "暂无数据", None
    except Exception as e:
        return "", f"资金流向：{e}"


@st.cache_data(ttl=600, show_spinner=False)
def get_dragon_tiger(ts_code: str) -> tuple[str, str | None]:
    pro = get_pro()
    if pro is None:
        return "", _ts_err
    try:
        df = pro.top_list(trade_date=ndays_ago(30), ts_code=ts_code,
                          fields="trade_date,name,close,pct_change,net_amount,reason")
        if df is not None and not df.empty:
            return df.head(10).to_string(index=False), None
        return "近30日无龙虎榜记录", None
    except Exception as e:
        return "龙虎榜暂不可用", f"龙虎榜：{e}"


# ══════════════════════════════════════════════════════════════════════════════
# K-LINE CHART
# ══════════════════════════════════════════════════════════════════════════════

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

    for ma, clr in [("MA5","#f97316"), ("MA20","#6366f1"), ("MA60","#a855f7")]:
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
        template="plotly_white", height=540,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#fafbff", paper_bgcolor="#ffffff",
        font=dict(family="Nunito,sans-serif", color="#6b7280", size=11),
        legend=dict(orientation="h", y=1.05, x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=50, b=15, l=10, r=10),
    )
    fig.update_xaxes(gridcolor="#e5e7eb", gridwidth=0.5, zeroline=False)
    fig.update_yaxes(gridcolor="#e5e7eb", gridwidth=0.5)
    st.plotly_chart(fig, use_container_width=True)


def price_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "暂无K线数据"
    d = df.copy()
    for p in [5, 20, 60]:
        d[f"MA{p}"] = d["收盘"].rolling(p).mean()
    lt = d.iloc[-1]

    def pct(n):
        if len(d) <= n: return "N/A"
        return f"{(d.iloc[-1]['收盘']/d.iloc[-n]['收盘']-1)*100:.2f}%"

    ma_arr = ("多头排列↑" if lt["MA5"]>lt["MA20"]>lt["MA60"]
              else "空头排列↓" if lt["MA5"]<lt["MA20"]<lt["MA60"]
              else "均线纠缠~")
    return "\n".join([
        f"最新收盘: {lt['收盘']:.2f}元",
        f"5日:{pct(5)}  20日:{pct(20)}  60日:{pct(60)}",
        f"MA5={lt['MA5']:.2f}  MA20={lt['MA20']:.2f}  MA60={lt['MA60']:.2f} → {ma_arr}",
        f"60日区间: 最高{d.tail(60)['最高'].max():.2f} / 最低{d.tail(60)['最低'].min():.2f}",
        "",
        "近15日 OHLCV：",
        d.tail(15)[["日期","开盘","最高","最低","收盘","成交量","涨跌幅"]].to_string(index=False),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# AI ANALYSIS MODULES
# ══════════════════════════════════════════════════════════════════════════════

def analyze_expectation_gap(client, cfg, name, ts_code, info, news) -> tuple[str,str|None]:
    news_text = "\n".join(f"[{n.get('发布时间','')}] {n.get('新闻标题','')}"
                          for n in news[:12]) or "暂无最新新闻"
    info_str = json.dumps({k:v for k,v in info.items()}, ensure_ascii=False)[:1400]
    prompt = f"""你是中国顶级买方研究院首席分析师，专精A股预期差挖掘与市场博弈分析。

## 分析标的：{name}（{to_code6(ts_code)}）

## 公司基本信息
{info_str}

## 近期新闻动态
{news_text}

---
请结合上述信息及搜索到的最新信息，进行深度预期差分析（输出中文）：

### 一、当前核心炒作逻辑
详述当前市场炒作该股的核心叙事——是主题/概念驱动、业绩拐点、政策催化，还是资金博弈？逻辑强度与可持续性如何？

### 二、市场一致预期
目前市场对这只股的主流预期是什么？预期是否已经充分price in？

### 三、预期差所在（核心价值）
**🟢 超预期方向（潜在正向惊喜）：**
- （列出2-3个可能超出市场预期的具体因素）

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

### 六、综合结论（2-3句话）
"""
    return call_ai(client, cfg, prompt, max_tokens=3200)


def analyze_trend(client, cfg, name, ts_code, price_smry, capital, dragon) -> tuple[str,str|None]:
    prompt = f"""你是资深A股技术分析师，深谙量价关系、主力行为与资金博弈。

## 分析标的：{name}（{to_code6(ts_code)}）

## K线及量价数据
{price_smry}

## 主力资金流向（近15日）
{capital[:700] if capital else '暂无'}

## 龙虎榜记录（近30日）
{dragon[:400] if dragon else '无记录'}

---
请进行专业中短线技术与资金面综合分析（输出中文）：

### 一、K线形态识别
当前形态及关键支撑/压力位

### 二、均线系统解读
排列特征、金叉/死叉情况

### 三、量价关系分析
量能特征、量价配合健康度、主力信号

### 四、资金动向研判
净流入/流出趋势、龙虎榜含义、筹码成本区

### 五、中短线趋势研判

**📌 短线展望（1-2周）：**
- 趋势：看多/看空/震荡
- 买入参考：___元  止损：___元  目标：___元

**📌 中线展望（1-3个月）：**
- 趋势方向及理由
- 目标区间：___元 ~ ___元  支撑：___元

### 六、历史相似走势参考案例（3个）

**【案例1】**
- 股票：
- 相似背景：
- 相似特征：
- 后续走势：
- 参考意义：

**【案例2】**（同格式）

**【案例3】**（同格式）
"""
    return call_ai(client, cfg, prompt, max_tokens=3500)


def analyze_fundamentals(client, cfg, name, ts_code, info, financial) -> tuple[str,str|None]:
    info_str = json.dumps({k:v for k,v in info.items()}, ensure_ascii=False)[:1000]
    prompt = f"""你是专业A股基本面研究员，精通财务分析与估值体系。

## 分析标的：{name}（{to_code6(ts_code)}）

## 基本信息
{info_str}

## 财务数据
{financial[:2200] if financial else '暂无'}

---
请进行全面基本面剖析，用于筛除垃圾公司（输出中文）：

### 一、财务健康体检

| 维度 | 评估内容 | 近期表现/趋势 | 评级（⭐1-5）|
|-----|---------|------------|------------|
| 成长性 | 营收/净利润CAGR | | |
| 盈利质量 | 净利率、现金含量、扣非 | | |
| 偿债安全 | 资负率、流动/速动比 | | |
| 资本效率 | ROE近3年、ROIC | | |
| 现金流 | 经营现金流 vs 净利润 | | |

**财务健康评分：X / 10**

### 二、盈利质量深析
- 利润真实性、财务水分风险

### 三、核心竞争力评估
- 护城河类型及宽度
- 行业地位与竞争格局

### 四、估值分析
| 指标 | 当前值 | 历史分位 | 行业均值 | 判断 |
|-----|-------|--------|---------|-----|
| PE(TTM) | | | | |
| PB | | | | |
| PS | | | | |
| 股息率 | | | | |

**估值结论：** 低估/合理/偏贵/高估

### 五、风险预警雷达 🚨
1. 财务风险
2. 股东风险（减持/质押/解禁）
3. 经营风险
4. 估值风险

### 六、基本面裁决
**综合评分：X / 10**
**筛选结论：** ✅通过 / ❌不通过 / ⚠️谨慎
**核心理由：**
"""
    return call_ai(client, cfg, prompt, max_tokens=3200)


# ══════════════════════════════════════════════════════════════════════════════
# MoE DEBATE
# ══════════════════════════════════════════════════════════════════════════════

MOE_ROLES = [
    {"key":"trader",  "css":"r-trader", "badge":"⚡ 短线游资 · 闪电刀",
     "system":"你是A股短线游资操盘手「闪电刀」，时间维度1-10交易日。"
              "核心：题材热度、情绪共振、技术突破、龙头效应。判断直接，止损果断。"
              "语言简练带游资嗅觉，用「动力足不足」「有没有持续性」「跟不跟」等行话。"},
    {"key":"institution","css":"r-inst","badge":"🏛️ 中线机构 · 稳健先生",
     "system":"你是头部公募基金经理「稳健先生」，时间维度1-6个月。"
              "核心：基本面景气度+估值安全边际+政策配合。语言专业理性，注重数据逻辑链。"},
    {"key":"quant",   "css":"r-quant","badge":"🤖 量化资金 · Alpha机器",
     "system":"你是A股量化多因子研究员「Alpha机器」。"
              "基于数据和统计规律，关注动量/价值/质量/情绪/资金流因子，善用概率表述。"},
    {"key":"retail",  "css":"r-retail","badge":"👥 普通散户 · 韭菜代表 ⚠️反向指标",
     "system":"你是典型A股散户「韭菜代表」，你的观点是重要的反向指标！"
              "追涨杀跌，高点乐观底部恐慌。口语化，带散户焦虑/贪婪/侥幸心理。"},
]

CEO_SYSTEM = ("你是掌管300亿私募的顶级CEO，历经2008/2015/2018三次A股大崩盘，20年投资经验。"
              "深知散户情绪是最可靠的反向指标。给出明确、可操作、附具体价格的最终裁决。")


def run_moe(client, cfg, name, ts_code, analyses: dict) -> None:
    code6 = to_code6(ts_code)
    summary = f"""分析摘要：{name}（{code6}）
【预期差】{analyses.get('expectation','')[:900]}
【趋势】{analyses.get('trend','')[:900]}
【基本面】{analyses.get('fundamentals','')[:900]}"""

    role_results: dict[str, str] = {}
    ai_errors = []

    for role in MOE_ROLES:
        with st.spinner(f"{role['badge']} 发表观点中..."):
            prompt = f"""辩论标的：{name}（{code6}）
背景：{summary[:2200]}
---
从你的角色视角给出明确判断，控制在220字以内：
**核心判断：** 看多/看空/中性/观望
**主要依据（3条）：**
1.
2.
3.
**操作建议：**（具体操作+参考点位）
**最大风险：**（1个）
保持角色特色和语言风格。"""
            text, err = call_ai(client, cfg, prompt,
                                system=role["system"], max_tokens=700)
        if err:
            text = f"⚠️ 该角色分析失败：{err}"
            ai_errors.append(err)
        role_results[role["key"]] = text
        st.markdown(f"""<div class="role-card {role['css']}">
  <div class="role-badge">{role['badge']}</div>
  <div class="role-content">{text}</div>
</div>""", unsafe_allow_html=True)

    if ai_errors:
        st.markdown(f'<div class="status-banner warn">⚠️ 部分角色调用失败，建议切换模型重试：{ai_errors[0]}</div>',
                    unsafe_allow_html=True)

    st.markdown("---")

    roles_text = "\n\n".join(f"【{r['badge']}】\n{role_results.get(r['key'],'')}"
                              for r in MOE_ROLES)
    with st.spinner("👔 首席执行官 综合裁决中..."):
        ceo_prompt = f"""标的：{name}（{code6}）
四位专家观点：{roles_text}
背景：{summary[:1200]}
---
给出最终操作裁决。**散户（韭菜代表）的观点是反向指标，逆向参考。**

## 🎯 最终操作结论
**操作评级：** 强烈买入/买入/谨慎介入/持有观察/减持/回避
**裁决逻辑（3-4句）：**
**目标价体系：**
| 维度 | 价格 | 依据 |
|-----|-----|-----|
| 当前股价 | X.XX元 | — |
| 短线目标（1-2周）| | |
| 中线目标（1-3月）| | |
| 止损位 | | |
**仓位策略：** 建议仓位X%，介入方式：
**核心逻辑（2条）：**
**核心风险（2条）：**
**策略有效期：** ___个交易日，若[条件]则失效。"""

        ceo_text, ceo_err = call_ai(client, cfg, ceo_prompt, system=CEO_SYSTEM, max_tokens=1600)

    if ceo_err:
        ceo_text = f"⚠️ CEO裁决生成失败：{ceo_err}\n\n建议切换其他模型后重新尝试。"

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

def show_results(client, cfg):
    r      = st.session_state.get("analyses", {})
    name   = st.session_state.get("stock_name", "")
    tscode = st.session_state.get("stock_code", "")
    df     = st.session_state.get("price_df", pd.DataFrame())

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 预期差分析", "📈 K线 & 趋势", "📋 基本面", "🎯 MoE 辩论裁决",
    ])

    with tab1:
        content = r.get("expectation", "")
        if content:
            st.markdown(f'<div class="analysis-wrap">{content}</div>', unsafe_allow_html=True)
        else:
            st.info("点击「开始分析」后，预期差分析结果将显示在这里。")

    with tab2:
        render_kline(df, name, tscode)
        content = r.get("trend", "")
        if content:
            st.markdown("---")
            st.markdown(f'<div class="analysis-wrap">{content}</div>', unsafe_allow_html=True)

    with tab3:
        content = r.get("fundamentals", "")
        if content:
            st.markdown(f'<div class="analysis-wrap">{content}</div>', unsafe_allow_html=True)
        else:
            st.info("基本面分析结果将显示在这里。")

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
            st.info("💡 完成分析后，点击下方按钮启动四方辩论，获取带具体点位的操作结论。")
            st.caption("⚠️ 普通散户的观点将作为**反向指标**，首席执行官会逆向参考。")
            if not r:
                st.warning("请先点击「🚀 开始分析」完成股票分析。")
            elif client:
                if st.button("🎯 启动 MoE 辩论博弈", type="primary"):
                    run_moe(client, cfg, name, tscode, r)
            else:
                st.warning("⚠️ 当前模型 API Key 未配置，暂无法启动辩论。")


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
        st.markdown("### 🤖 选择分析模型")

        # Model selector
        selected_model = st.selectbox(
            "当前模型",
            options=MODEL_NAMES,
            index=0,   # 默认 Qwen
            key="selected_model",
            label_visibility="collapsed",
        )
        cfg = MODEL_CONFIGS[selected_model]

        # Model status
        has_key = bool(cfg["api_key"])
        if has_key:
            search_tip = "🌐 联网搜索已开启" if cfg["supports_search"] else "📚 仅内部知识"
            st.markdown(f'<div class="model-badge ok">✅ {cfg["note"]} &nbsp;·&nbsp; {search_tip}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="model-badge err">⚠️ API Key 待配置，请在 app.py 中填写</div>',
                        unsafe_allow_html=True)
            st.caption("暂无法使用AI分析，K线图仍可正常查看")

        # Tushare status
        st.markdown("### 📡 数据源状态")
        if ts_ok():
            st.markdown('<div class="model-badge ok">✅ Tushare 连接正常</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="model-badge err">❌ Tushare 异常</div>',
                        unsafe_allow_html=True)
            st.caption(f"原因：{_ts_err}")
            st.caption("数据获取受限，请检查网络或 Token")

        st.markdown("---")
        st.markdown("### 📖 使用方法")
        st.markdown("""
**① 上方选择分析模型**

**② 输入股票代码或名称**
> 例：`600519` 或 `贵州茅台`

**③ 点击「开始分析」**
> 约 1-3 分钟完成分析

**④ 切换标签查看各模块**

**⑤ 「MoE辩论」标签**
> 获取四方辩论 + 操作结论
""")

        st.markdown("---")
        st.markdown("""
<div class="disclaimer">
⚠️ <strong>免责声明</strong><br>
本工具仅供学习研究，不构成任何投资建议。A股市场风险较大，请独立判断，自行承担投资盈亏。
</div>
""", unsafe_allow_html=True)

    # ── Tushare global warning ────────────────────────────────────────────────
    if not ts_ok():
        st.markdown(f"""<div class="status-banner error">
  ❌ <strong>Tushare 数据源异常</strong>：{_ts_err}<br>
  K线图和财务数据将无法显示，请检查网络连接或联系管理员检查 Token。
</div>""", unsafe_allow_html=True)

    # ── Search Bar ────────────────────────────────────────────────────────────
    col_in, col_btn, col_clr = st.columns([5, 1.3, 0.8])
    with col_in:
        query = st.text_input(
            "搜索股票", label_visibility="collapsed",
            placeholder="🔍  输入股票代码（如 000858）或名称（如 五粮液）…",
            key="query_input",
        )
    with col_btn:
        start = st.button("🚀 开始分析", type="primary", use_container_width=True)
    with col_clr:
        if st.button("🗑 重置", use_container_width=True):
            for k in ["analyses","stock_code","stock_name","price_df","stock_info","moe_results"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Run Analysis ──────────────────────────────────────────────────────────
    if start and query:
        client, cfg_now, ai_err = get_ai_client(selected_model)

        # Warn if AI not available, but don't stop — K-line still works
        if ai_err:
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>AI 模型暂不可用</strong>：{ai_err}<br>
  K线图将正常显示，AI深度分析跳过。建议在左侧切换其他模型后重试。
</div>""", unsafe_allow_html=True)

        if not ts_ok():
            st.markdown(f"""<div class="status-banner error">
  ❌ <strong>Tushare 数据源不可用</strong>，无法获取行情数据。请检查网络连接。
</div>""", unsafe_allow_html=True)
            st.stop()

        st.session_state.pop("moe_results", None)

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

            st.write("▶ 新闻资讯...")
            news, e = get_news(ts_code, name)
            if e: data_errors.append(e)

            st.write("▶ 主力资金流向...")
            cap, e = get_capital_flow(ts_code)
            if e: data_errors.append(e)

            st.write("▶ 龙虎榜...")
            dragon, e = get_dragon_tiger(ts_code)
            if e: data_errors.append(e)

            s.update(label="✅ 数据获取完成！", state="complete")

        if data_errors:
            errs_text = " | ".join(data_errors[:3])
            st.markdown(f"""<div class="status-banner warn">
  ⚠️ <strong>部分数据获取受限</strong>（不影响主要功能）：{errs_text}
</div>""", unsafe_allow_html=True)

        # Stock metrics header
        st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")
        metrics = [
            ("最新价", info.get("最新价(元)","—")),
            ("市盈率TTM", info.get("市盈率TTM","—")),
            ("市净率PB", info.get("市净率PB","—")),
            ("市销率PS", info.get("市销率PS","—")),
            ("换手率", info.get("换手率(%)","—")),
            ("行业", info.get("行业","—")),
        ]
        cols = st.columns(6)
        for col, (label, val) in zip(cols, metrics):
            with col:
                st.metric(label, str(val)[:14])

        # AI Analysis (only if client available)
        analyses: dict[str, str] = {}
        if client:
            psmry = price_summary(df)
            with st.status(f"🤖 {selected_model} 深度分析中（约1-3分钟）...",
                           expanded=True) as ai_s:
                st.write("1/3  🔍 预期差分析（搜索最新资讯）...")
                text, err = analyze_expectation_gap(client, cfg_now, name, ts_code, info, news)
                if err:
                    st.markdown(f'<div class="status-banner warn">⚠️ 预期差分析失败：{err} — 建议切换模型重试</div>',
                                unsafe_allow_html=True)
                    text = f"⚠️ 分析失败：{err}\n\n请在左侧切换其他模型后重新分析。"
                analyses["expectation"] = text

                st.write("2/3  📈 趋势研判...")
                text, err = analyze_trend(client, cfg_now, name, ts_code,
                                          psmry, cap, dragon)
                if err:
                    st.markdown(f'<div class="status-banner warn">⚠️ 趋势分析失败：{err}</div>',
                                unsafe_allow_html=True)
                    text = f"⚠️ 分析失败：{err}"
                analyses["trend"] = text

                st.write("3/3  📋 基本面剖析...")
                text, err = analyze_fundamentals(client, cfg_now, name, ts_code, info, fin)
                if err:
                    st.markdown(f'<div class="status-banner warn">⚠️ 基本面分析失败：{err}</div>',
                                unsafe_allow_html=True)
                    text = f"⚠️ 分析失败：{err}"
                analyses["fundamentals"] = text

                ai_s.update(label="✅ AI分析完成！", state="complete")

            st.success("✅ 分析完成！切换上方标签查看详情，进入「MoE辩论裁决」获取操作建议。")
        else:
            st.markdown(f"""<div class="status-banner info">
  ℹ️ <strong>AI分析已跳过</strong>（API Key 未配置）。K线图已在「K线 & 趋势」标签中生成，可供参考。<br>
  请在左侧切换已配置 API Key 的模型，然后重新点击「开始分析」。
</div>""", unsafe_allow_html=True)

        st.session_state["analyses"] = analyses

    # ── Show Results ──────────────────────────────────────────────────────────
    if st.session_state.get("analyses") is not None or st.session_state.get("price_df") is not None:
        if not start:
            ts_code = st.session_state.get("stock_code","")
            name    = st.session_state.get("stock_name","")
            if name:
                st.markdown(f"### {name} &nbsp; `{to_code6(ts_code)}`")

        _, cfg_now, _ = get_ai_client(selected_model)
        client, _, _ = get_ai_client(selected_model)
        show_results(client, cfg_now)


if __name__ == "__main__":
    main()
