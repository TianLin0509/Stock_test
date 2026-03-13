"""数据层 — Tushare 优先，akshare 备用，东方财富保底"""

import streamlit as st
import pandas as pd
import tushare as ts
import re
import os
from datetime import datetime, timedelta


# ══════════════════════════════════════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════════════════════════════════════

TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN", "")
TUSHARE_URL   = st.secrets.get("TUSHARE_URL", "http://lianghua.nanyangqiankun.top")


def _init_tushare():
    try:
        import time as _time
        import requests as _req

        ts.set_token(TUSHARE_TOKEN)
        p = ts.pro_api(TUSHARE_TOKEN)
        p._DataApi__token = TUSHARE_TOKEN
        p._DataApi__http_url = TUSHARE_URL

        # 增大 tushare 底层 requests 超时（云端跨境访问可能较慢）
        _orig_post = _req.post
        def _patched_post(*a, **kw):
            kw.setdefault("timeout", 30)
            return _orig_post(*a, **kw)
        _req.post = _patched_post

        for attempt in range(1, 6):
            try:
                test = p.trade_cal(exchange="SSE", start_date="20240101", end_date="20240103")
                if test is not None and not test.empty:
                    return p, None
            except Exception as e:
                if attempt < 5:
                    _time.sleep(3)
        return None, "Tushare 接口返回空，请检查 Token 或网络"
    except Exception as e:
        return None, f"Tushare 初始化失败：{e}"


_pro, _ts_err = _init_tushare()

# 数据源状态追踪
_data_source = "tushare" if _pro else "fallback"


def ts_ok() -> bool:
    """Tushare 或备用源是否可用（始终返回 True，因为有三层兜底）"""
    return True


def get_ts_error() -> str:
    return _ts_err or ""


def get_data_source() -> str:
    """返回当前实际使用的数据源"""
    return _data_source


def get_pro():
    return _pro


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 通用重试
# ══════════════════════════════════════════════════════════════════════════════

def _retry_call(fn, retries=3, delay=1):
    import time as _time
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt < retries:
                _time.sleep(delay)
                delay *= 2
            else:
                raise


# ══════════════════════════════════════════════════════════════════════════════
# 三层兜底调度器
# ══════════════════════════════════════════════════════════════════════════════

def _try_with_fallback(tushare_fn, akshare_fn, eastmoney_fn=None, label="数据"):
    """依次尝试 Tushare → akshare → 东方财富，返回第一个成功的结果"""
    global _data_source

    # 第一层：Tushare
    if _pro is not None:
        try:
            result, err = tushare_fn()
            if err is None:
                _data_source = "tushare"
                return result, None
        except Exception:
            pass

    # 第二层：akshare
    if akshare_fn is not None:
        try:
            result, err = akshare_fn()
            if err is None:
                _data_source = "akshare"
                return result, None
        except Exception:
            pass

    # 第三层：东方财富
    if eastmoney_fn is not None:
        try:
            result, err = eastmoney_fn()
            if err is None:
                _data_source = "eastmoney"
                return result, None
        except Exception:
            pass

    _data_source = "unavailable"
    return (pd.DataFrame() if label == "K线" else ({} if label == "基本信息" else "")), \
           f"所有数据源均不可用（{label}）"


# ══════════════════════════════════════════════════════════════════════════════
# 数据获取（带三层兜底）
# ══════════════════════════════════════════════════════════════════════════════

_STOCK_LIST_CSV = os.path.join(os.path.dirname(__file__), "stock_list.csv")


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list() -> tuple[pd.DataFrame, str | None]:
    """优先读本地 CSV → Tushare API → akshare"""
    if os.path.exists(_STOCK_LIST_CSV):
        try:
            df = pd.read_csv(_STOCK_LIST_CSV)
            for col in ["ts_code", "symbol", "name", "industry", "area", "market"]:
                if col not in df.columns:
                    df[col] = ""
            return df, None
        except Exception:
            pass

    if _pro is not None:
        try:
            df = _retry_call(
                lambda: _pro.stock_basic(
                    exchange="", list_status="L",
                    fields="ts_code,symbol,name,industry,area,market"
                ),
                retries=5, delay=2,
            )
            if df is not None and not df.empty:
                return df, None
        except Exception:
            pass

    # akshare 兜底
    from data.fallback import ak_get_stock_list
    return ak_get_stock_list()


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


@st.cache_data(ttl=600, show_spinner=False)
def get_basic_info(ts_code: str) -> tuple[dict, str | None]:
    from data.fallback import ak_get_basic_info, em_get_basic_info

    def _tushare():
        if _pro is None:
            return {}, _ts_err
        result = {}
        err_msgs = []

        df_list, _ = load_stock_list()
        if not df_list.empty:
            m = df_list[df_list["ts_code"] == ts_code]
            if not m.empty:
                row = m.iloc[0]
                result.update({"名称": row.get("name", ""), "行业": row.get("industry", ""),
                               "地区": row.get("area", ""), "市场": row.get("market", "")})
        try:
            df_db = _retry_call(
                lambda: _pro.daily_basic(
                    ts_code=ts_code, start_date=ndays_ago(10), end_date=today(),
                    fields="ts_code,trade_date,close,pe_ttm,pb,ps_ttm,total_mv,turnover_rate,volume_ratio"
                ),
                retries=3, delay=1,
            )
            if df_db is not None and not df_db.empty:
                row = df_db.iloc[0]
                mv = row.get("total_mv")
                result.update({
                    "最新价(元)":   str(row.get("close", "N/A")),
                    "市盈率TTM":    str(row.get("pe_ttm", "N/A")),
                    "市净率PB":     str(row.get("pb", "N/A")),
                    "市销率PS":     str(row.get("ps_ttm", "N/A")),
                    "总市值(万元)": f"{float(mv):,.0f}" if mv else "N/A",
                    "换手率(%)":    str(row.get("turnover_rate", "N/A")),
                    "量比":         str(row.get("volume_ratio", "N/A")),
                })
                return result, None
        except Exception as e:
            err_msgs.append(f"估值数据：{e}")

        if result:
            return result, ("; ".join(err_msgs) if err_msgs else None)
        return {}, "; ".join(err_msgs) if err_msgs else "Tushare 无数据"

    return _try_with_fallback(
        _tushare,
        lambda: ak_get_basic_info(ts_code),
        lambda: em_get_basic_info(ts_code),
        label="基本信息",
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_price_df(ts_code: str, days: int = 140) -> tuple[pd.DataFrame, str | None]:
    from data.fallback import ak_get_price_df, em_get_price_df

    def _tushare():
        if _pro is None:
            return pd.DataFrame(), _ts_err
        df = _retry_call(
            lambda: _pro.daily(ts_code=ts_code, start_date=ndays_ago(days), end_date=today()),
            retries=3, delay=1,
        )
        if df is None or df.empty:
            return pd.DataFrame(), "未获取到K线数据"
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df.rename(columns={
            "trade_date": "日期", "open": "开盘", "high": "最高",
            "low": "最低", "close": "收盘", "vol": "成交量",
            "pct_chg": "涨跌幅", "amount": "成交额",
        })
        return df, None

    return _try_with_fallback(
        _tushare,
        lambda: ak_get_price_df(ts_code, days),
        lambda: em_get_price_df(ts_code, days),
        label="K线",
    )


@st.cache_data(ttl=600, show_spinner=False)
def get_financial(ts_code: str) -> tuple[str, str | None]:
    from data.fallback import ak_get_financial

    def _tushare():
        if _pro is None:
            return "", _ts_err
        parts, errs = [], []
        try:
            df = _retry_call(
                lambda: _pro.fina_indicator(
                    ts_code=ts_code,
                    fields="end_date,roe,roa,grossprofit_margin,netprofit_margin,"
                           "debt_to_assets,current_ratio,quick_ratio,revenue_yoy,netprofit_yoy,basic_eps"
                ),
                retries=3, delay=1,
            )
            if df is not None and not df.empty:
                parts.append("核心财务指标（近5期）：\n" + df.head(5).to_string(index=False))
        except Exception as e:
            errs.append(f"财务指标：{e}")
        try:
            rpt = str((datetime.now().year - 1) * 10000 + 1231)
            df2 = _retry_call(
                lambda: _pro.income(
                    ts_code=ts_code, start_date=str(int(rpt) - 30000), end_date=rpt,
                    fields="end_date,total_revenue,operate_profit,n_income,n_income_attr_p"
                ),
                retries=3, delay=1,
            )
            if df2 is not None and not df2.empty:
                parts.append("利润表摘要（近4期）：\n" + df2.head(4).to_string(index=False))
        except Exception as e:
            errs.append(f"利润表：{e}")

        if parts:
            return "\n\n".join(parts), None
        return "", "; ".join(errs) if errs else "Tushare 无财务数据"

    return _try_with_fallback(
        _tushare,
        lambda: ak_get_financial(ts_code),
        None,
        label="财务",
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_capital_flow(ts_code: str) -> tuple[str, str | None]:
    from data.fallback import ak_get_capital_flow

    def _tushare():
        if _pro is None:
            return "", _ts_err
        df = _retry_call(
            lambda: _pro.moneyflow(
                ts_code=ts_code, start_date=ndays_ago(20), end_date=today(),
                fields="trade_date,buy_sm_amount,buy_md_amount,buy_lg_amount,"
                       "buy_elg_amount,sell_sm_amount,sell_md_amount,sell_lg_amount,"
                       "sell_elg_amount,net_mf_amount"
            ),
            retries=3, delay=1,
        )
        if df is not None and not df.empty:
            return df.sort_values("trade_date").tail(15).to_string(index=False), None
        return "暂无数据", None

    return _try_with_fallback(
        _tushare,
        lambda: ak_get_capital_flow(ts_code),
        None,
        label="资金流向",
    )


@st.cache_data(ttl=600, show_spinner=False)
def get_dragon_tiger(ts_code: str) -> tuple[str, str | None]:
    """龙虎榜仅 Tushare 有，无备用源"""
    if _pro is None:
        return "龙虎榜暂不可用（Tushare 不可用）", None
    try:
        df = _retry_call(
            lambda: _pro.top_list(trade_date=ndays_ago(30), ts_code=ts_code,
                                  fields="trade_date,name,close,pct_change,net_amount,reason"),
            retries=3, delay=1,
        )
        if df is not None and not df.empty:
            return df.head(10).to_string(index=False), None
        return "近30日无龙虎榜记录", None
    except Exception as e:
        return "龙虎榜暂不可用", f"龙虎榜：{e}"


def price_summary(df: pd.DataFrame) -> str:
    """生成K线数据的文本摘要，供AI分析使用"""
    if df.empty:
        return "暂无K线数据"
    d = df.copy()
    for p in [5, 20, 60]:
        d[f"MA{p}"] = d["收盘"].rolling(p).mean()
    lt = d.iloc[-1]

    def pct(n):
        if len(d) <= n: return "N/A"
        return f"{(d.iloc[-1]['收盘'] / d.iloc[-n]['收盘'] - 1) * 100:.2f}%"

    ma_arr = ("多头排列↑" if lt["MA5"] > lt["MA20"] > lt["MA60"]
              else "空头排列↓" if lt["MA5"] < lt["MA20"] < lt["MA60"]
              else "均线纠缠~")
    return "\n".join([
        f"最新收盘: {lt['收盘']:.2f}元",
        f"5日:{pct(5)}  20日:{pct(20)}  60日:{pct(60)}",
        f"MA5={lt['MA5']:.2f}  MA20={lt['MA20']:.2f}  MA60={lt['MA60']:.2f} → {ma_arr}",
        f"60日区间: 最高{d.tail(60)['最高'].max():.2f} / 最低{d.tail(60)['最低'].min():.2f}",
        "",
        "近15日 OHLCV：",
        d.tail(15)[["日期", "开盘", "最高", "最低", "收盘", "成交量", "涨跌幅"]].to_string(index=False),
    ])
