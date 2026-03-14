"""分析归档 — 保存完整分析结果供回测使用

每次分析完成时自动归档，带质量校验（截断/失败的分析不保存）。
归档文件: data/archive/{date}_{code6}_{user}.json
索引文件: data/archive/_index.jsonl (JSON Lines, pandas 一行加载)
"""

import json
import re
import threading
from datetime import datetime
from pathlib import Path

ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "archive"
INDEX_FILE = ARCHIVE_DIR / "_index.jsonl"
_lock = threading.Lock()

# ── 质量校验：确认分析输出完整，未被截断 ──────────────────────────────

# 每种分析类型的"完成标志"——至少命中一个才算完整
_COMPLETION_MARKERS = {
    "expectation": [
        r"综合结论", r"三情景分析", r"催化事件", r"概率估计",
        r"乐观.*中性.*悲观", r"🟢.*🔴",
    ],
    "trend": [
        r"中线展望", r"短线展望", r"目标.*元", r"止损",
        r"趋势研判", r"案例",
    ],
    "fundamentals": [
        r"基本面裁决", r"综合评分.*\/\s*10", r"筛选结论",
        r"✅|❌|⚠️", r"通过|不通过|谨慎",
    ],
    "sentiment": [
        r"舆情综合结论", r"情绪偏向", r"散户.*指标",
        r"看多方|看空方", r"整体关注度",
    ],
    "sector": [
        r"板块联动", r"竞争地位", r"龙头", r"操作建议",
        r"产业链", r"板块.*阶段",
    ],
    "holders": [
        r"综合评估", r"机构态度", r"风险等级",
        r"质押", r"增持|减持",
    ],
}


def _is_complete(key: str, text: str) -> bool:
    """检查分析文本是否完整（非截断/非失败）"""
    if not text or len(text) < 200:
        return False
    # 失败标记
    if text.startswith("⚠️") and ("失败" in text[:50] or "异常" in text[:50]):
        return False
    # 检查完成标志
    markers = _COMPLETION_MARKERS.get(key, [])
    if not markers:
        return len(text) >= 500  # 无特定标志的类型，至少500字
    return any(re.search(m, text) for m in markers)


# ── 归档保存 ─────────────────────────────────────────────────────────

def save_archive(session_state: dict):
    """将当前完整分析结果归档保存（仅保存通过质量校验的分析）"""
    stock_name = session_state.get("stock_name", "")
    stock_code = session_state.get("stock_code", "")
    if not stock_name or not stock_code:
        return None

    analyses = session_state.get("analyses", {})

    # 只归档通过质量校验的分析
    valid_keys = [k for k in ["expectation", "trend", "fundamentals",
                               "sentiment", "sector", "holders"]
                  if analyses.get(k) and _is_complete(k, analyses[k])]
    if not valid_keys:
        return None

    now = datetime.now()
    code6 = stock_code.split(".")[0] if "." in stock_code else stock_code
    username = session_state.get("current_user", "anonymous")

    # 避免重复归档同一股票同一用户（5分钟内）
    archive_key = f"{code6}_{username}"
    last_ts = session_state.get("_last_archive", {}).get(archive_key, "")
    if last_ts:
        try:
            elapsed = (now - datetime.fromisoformat(last_ts)).total_seconds()
            if elapsed < 300:  # 5分钟内已归档过，更新而非新建
                return _update_archive(session_state, valid_keys, archive_key)
        except (ValueError, TypeError):
            pass

    # 股价快照
    info = dict(session_state.get("stock_info", {}))
    import pandas as pd
    price_df = session_state.get("price_df", pd.DataFrame())
    price_snapshot = {}
    if not price_df.empty:
        latest = price_df.iloc[-1]
        price_snapshot = {
            "date": str(latest.get("日期", "")),
            "open": float(latest.get("开盘", 0)),
            "high": float(latest.get("最高", 0)),
            "low": float(latest.get("最低", 0)),
            "close": float(latest.get("收盘", 0)),
            "volume": float(latest.get("成交量", 0)),
            "pct_chg": float(latest.get("涨跌幅", 0)) if "涨跌幅" in latest.index else 0,
        }

    # MoE结果（也做质量校验）
    moe = session_state.get("moe_results", {})
    moe_data = None
    if moe.get("done"):
        ceo = moe.get("ceo", "")
        # CEO裁决必须包含操作评级才算完整
        if ceo and re.search(r"操作评级|强烈买入|买入|谨慎介入|持有观察|减持|回避", ceo):
            moe_data = {
                "roles": dict(moe.get("roles", {})),
                "ceo": ceo,
            }

    # 完整归档记录
    record = {
        "archive_ts": now.isoformat(timespec="seconds"),
        "archive_date": now.strftime("%Y-%m-%d"),
        "username": username,
        "model": session_state.get("selected_model", ""),
        "stock_code": stock_code,
        "stock_name": stock_name,
        "stock_info": info,
        "price_snapshot": price_snapshot,
        "analyses": {k: analyses[k] for k in valid_keys},
        "analyses_validated": valid_keys,
        "moe_results": moe_data,
    }

    # 写入归档文件
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{code6}_{username}.json"
    filepath = ARCHIVE_DIR / filename

    with _lock:
        filepath.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _append_index(filename, record, info, price_snapshot, valid_keys, moe_data)

    # 记录归档时间，防重复
    if "_last_archive" not in session_state:
        session_state["_last_archive"] = {}
    session_state["_last_archive"][archive_key] = now.isoformat()
    session_state["_last_archive_file"] = filename

    return filename


def _update_archive(session_state, new_valid_keys, archive_key):
    """更新最近一次归档（同一股票5分钟内有新分析完成时）"""
    last_file = session_state.get("_last_archive_file", "")
    if not last_file:
        return None

    filepath = ARCHIVE_DIR / last_file
    if not filepath.exists():
        return None

    with _lock:
        try:
            record = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            return None

        analyses = session_state.get("analyses", {})
        for k in new_valid_keys:
            record["analyses"][k] = analyses[k]
            if k not in record.get("analyses_validated", []):
                record["analyses_validated"].append(k)

        # 更新MoE
        moe = session_state.get("moe_results", {})
        if moe.get("done") and not record.get("moe_results"):
            ceo = moe.get("ceo", "")
            if ceo and re.search(r"操作评级|强烈买入|买入|谨慎介入|持有观察|减持|回避", ceo):
                record["moe_results"] = {
                    "roles": dict(moe.get("roles", {})),
                    "ceo": ceo,
                }

        record["archive_ts"] = datetime.now().isoformat(timespec="seconds")
        filepath.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return last_file


def _append_index(filename, record, info, price_snapshot, valid_keys, moe_data):
    """追加索引行"""
    index_entry = {
        "file": filename,
        "ts": record["archive_ts"],
        "date": record["archive_date"],
        "username": record["username"],
        "model": record["model"],
        "stock_code": record["stock_code"],
        "stock_name": record["stock_name"],
        "close": price_snapshot.get("close", 0),
        "pe_ttm": info.get("市盈率TTM", ""),
        "pb": info.get("市净率PB", ""),
        "analyses_done": valid_keys,
        "has_moe": moe_data is not None,
    }
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")


# ── 读取接口 ─────────────────────────────────────────────────────────

def load_index():
    """加载索引为 pandas DataFrame"""
    import pandas as pd
    if not INDEX_FILE.exists():
        return pd.DataFrame()
    records = []
    for line in INDEX_FILE.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return pd.DataFrame(records) if records else pd.DataFrame()


def load_archive(filename: str) -> dict:
    """加载单个归档文件"""
    path = ARCHIVE_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_archive_stats() -> dict:
    """归档统计"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = [f for f in ARCHIVE_DIR.glob("*.json")]
    total_size = sum(f.stat().st_size for f in files) if files else 0
    return {
        "count": len(files),
        "size_mb": round(total_size / 1024 / 1024, 2),
    }
