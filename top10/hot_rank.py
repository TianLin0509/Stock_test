"""数据获取 — 人气榜 + 成交额榜（优先 Tushare，备选东财/akshare）"""

import pandas as pd
import streamlit as st


@st.cache_data(ttl=1800, show_spinner=False)
def get_hot_rank(top_n: int = 100) -> tuple[pd.DataFrame, str | None]:
    """东方财富人气榜 Top N"""
    try:
        import akshare as ak
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return pd.DataFrame(), "人气榜数据为空"
        df = df.head(top_n)
        df.columns = ["排名", "代码", "股票名称", "最新价", "涨跌额", "涨跌幅"]
        # 代码标准化: SH600519 -> 600519
        df["代码"] = df["代码"].str.replace(r"^(SH|SZ|BJ)", "", regex=True)
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"人气榜获取失败：{e}"


@st.cache_data(ttl=1800, show_spinner=False)
def get_volume_rank(top_n: int = 100) -> tuple[pd.DataFrame, str | None]:
    """成交额排名 Top N — 优先 Tushare，备选东方财富"""
    # 优先 Tushare
    try:
        from top10.tushare_data import get_volume_rank_tushare, ts_ok
        if ts_ok():
            df, err = get_volume_rank_tushare(top_n)
            if err is None and not df.empty:
                return df, None
    except Exception:
        pass

    # 备选：东方财富 HTTP 接口
    try:
        return _get_volume_rank_eastmoney(top_n)
    except Exception:
        return _get_volume_rank_akshare(top_n)


def _get_volume_rank_eastmoney(top_n: int) -> tuple[pd.DataFrame, str | None]:
    """东方财富 HTTP 接口获取成交额排名"""
    import requests as req
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": top_n, "po": 1,
        "np": 1, "fltt": 2, "invt": 2,
        "fid": "f6",  # 按成交额排序
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f2,f3,f5,f6,f8,f9,f10,f12,f14,f20,f23,f62",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    resp = req.get(url, params=params, timeout=15)
    data = resp.json().get("data", {})
    items = data.get("diff", [])
    if not items:
        return pd.DataFrame(), "成交额榜数据为空"

    def _safe_num(v, default=0):
        if v is None or v == "-" or isinstance(v, str):
            return default
        return v

    rows = []
    for i, item in enumerate(items, 1):
        net_flow = _safe_num(item.get("f62", 0))
        mkt_cap = _safe_num(item.get("f20", 0))
        rows.append({
            "排名": i,
            "代码": item.get("f12", ""),
            "股票名称": item.get("f14", ""),
            "最新价": item.get("f2", 0),
            "涨跌幅": item.get("f3", 0),
            "成交额(亿)": round(_safe_num(item.get("f6", 0)) / 1e8, 2),
            "换手率": _safe_num(item.get("f8", 0)),
            "量比": _safe_num(item.get("f10", 0)),
            "市盈率": _safe_num(item.get("f9", 0)),
            "总市值(亿)": round(mkt_cap / 1e8, 1) if mkt_cap else 0,
            "主力净流入(万)": round(net_flow / 1e4, 2) if net_flow else 0,
        })
    return pd.DataFrame(rows), None


def _get_volume_rank_akshare(top_n: int) -> tuple[pd.DataFrame, str | None]:
    """akshare 备用方案获取成交额排名"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return pd.DataFrame(), "全量行情获取失败"
        df = df.sort_values("成交额", ascending=False).head(top_n).reset_index(drop=True)
        result = pd.DataFrame({
            "排名": range(1, len(df) + 1),
            "代码": df["代码"].values,
            "股票名称": df["名称"].values,
            "最新价": df["最新价"].values,
            "涨跌幅": df["涨跌幅"].values,
            "成交额(亿)": (df["成交额"] / 1e8).round(2).values,
        })
        return result, None
    except Exception as e:
        return pd.DataFrame(), f"成交额榜获取失败（备用方案也失败）：{e}"


def merge_candidates(hot_df: pd.DataFrame, vol_df: pd.DataFrame) -> pd.DataFrame:
    """合并人气榜和成交额榜，去重，双榜股票标记为'双榜'"""
    if hot_df.empty and vol_df.empty:
        return pd.DataFrame()

    # 以人气榜为基础
    if not hot_df.empty:
        merged = hot_df[["代码", "股票名称", "最新价", "涨跌幅"]].copy()
        merged["来源"] = "人气榜"
        merged["人气排名"] = hot_df["排名"]
    else:
        merged = pd.DataFrame()

    # 处理成交额榜
    if not vol_df.empty:
        v = vol_df[["代码", "股票名称", "最新价", "涨跌幅"]].copy()
        v["成交额排名"] = vol_df["排名"]
        if "成交额(亿)" in vol_df.columns:
            v["成交额(亿)"] = vol_df["成交额(亿)"]

        if not merged.empty:
            # 双榜股票：补充成交额信息，标记为"双榜"
            both_mask = merged["代码"].isin(v["代码"])
            merged.loc[both_mask, "来源"] = "双榜"

            v_indexed = v.set_index("代码")
            merged["成交额排名"] = merged["代码"].map(v_indexed["成交额排名"].to_dict())
            for col in ["成交额(亿)", "换手率", "量比", "市盈率", "总市值(亿)", "主力净流入(万)"]:
                if col in v.columns:
                    merged[col] = merged["代码"].map(v_indexed[col].to_dict())

            # 仅成交额榜的股票追加
            new_only = v[~v["代码"].isin(merged["代码"])].copy()
            if not new_only.empty:
                new_only["来源"] = "成交额榜"
                merged = pd.concat([merged, new_only], ignore_index=True)
        else:
            v["来源"] = "成交额榜"
            merged = v

    # 补充所有股票的成交额和成交额排名
    merged = _fill_volume_data(merged)

    # 所有浮点数统一保留两位小数
    for col in ["最新价", "涨跌幅", "成交额(亿)", "换手率", "量比",
                "市盈率", "总市值(亿)", "主力净流入(万)"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").round(2)

    # 排名列转整数
    for col in ["人气排名", "成交额排名"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    return merged.reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def _get_all_volume_data() -> pd.DataFrame:
    """全 A 股成交额排名 — 优先 Tushare，备选东方财富"""
    # 优先 Tushare
    try:
        from top10.tushare_data import get_all_volume_data_tushare, ts_ok
        if ts_ok():
            df = get_all_volume_data_tushare()
            if not df.empty:
                return df
    except Exception:
        pass

    # 备选：东方财富
    return _get_all_volume_data_eastmoney()


def _get_all_volume_data_eastmoney() -> pd.DataFrame:
    """从东方财富获取全 A 股按成交额排序的行情数据（含排名）"""
    try:
        import requests as req
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1, "pz": 5000, "po": 1,
            "np": 1, "fltt": 2, "invt": 2,
            "fid": "f6",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f6,f8,f10,f12,f62",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
        resp = req.get(url, params=params, timeout=15)
        items = resp.json().get("data", {}).get("diff", [])
        if not items:
            return pd.DataFrame()

        def _safe(v):
            if v is None or v == "-" or isinstance(v, str):
                return 0
            return v

        rows = []
        for i, item in enumerate(items, 1):
            code = item.get("f12", "")
            if not code:
                continue
            f6 = _safe(item.get("f6", 0))
            f62 = _safe(item.get("f62", 0))
            rows.append({
                "代码": code,
                "成交额排名_all": i,
                "成交额(亿)_all": round(f6 / 1e8, 2) if f6 else 0,
                "换手率_all": round(_safe(item.get("f8", 0)), 2),
                "量比_all": round(_safe(item.get("f10", 0)), 2),
                "主力净流入(万)_all": round(f62 / 1e4, 2) if f62 else 0,
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _fill_volume_data(df: pd.DataFrame) -> pd.DataFrame:
    """为所有候选股票补充成交额、成交额排名等数据"""
    if df.empty:
        return df

    all_vol = _get_all_volume_data()
    if all_vol.empty:
        return df

    vol_indexed = all_vol.set_index("代码")

    # 补充成交额排名（所有股票都补）
    if "成交额排名" not in df.columns:
        df["成交额排名"] = None
    mask_no_rank = df["成交额排名"].isna()
    if mask_no_rank.any():
        df.loc[mask_no_rank, "成交额排名"] = df.loc[mask_no_rank, "代码"].map(
            vol_indexed["成交额排名_all"].to_dict()
        )

    # 补充成交额和其他指标（只补缺失的）
    for col, src_col in [("成交额(亿)", "成交额(亿)_all"),
                          ("换手率", "换手率_all"),
                          ("量比", "量比_all"),
                          ("主力净流入(万)", "主力净流入(万)_all")]:
        if col not in df.columns:
            df[col] = None
        mask = df[col].isna() | (df[col] == 0)
        if mask.any():
            df.loc[mask, col] = df.loc[mask, "代码"].map(
                vol_indexed[src_col].to_dict()
            )

    return df
