"""分析归档 — 保存完整分析结果供回测使用

每次分析存为一个 JSON 文件: data/archive/{date}_{code6}_{user}.json
同时维护一个索引文件 data/archive/_index.jsonl (JSON Lines, 方便 pandas 读取)
"""

import json
import threading
from datetime import datetime
from pathlib import Path

ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "archive"
INDEX_FILE = ARCHIVE_DIR / "_index.jsonl"
_lock = threading.Lock()


def save_archive(session_state: dict):
    """将当前完整分析结果归档保存"""
    stock_name = session_state.get("stock_name", "")
    stock_code = session_state.get("stock_code", "")
    if not stock_name or not stock_code:
        return

    analyses = session_state.get("analyses", {})
    done_keys = [k for k in ["expectation", "trend", "fundamentals",
                              "sentiment", "sector", "holders"] if analyses.get(k)]
    if not done_keys:
        return

    now = datetime.now()
    code6 = stock_code.split(".")[0] if "." in stock_code else stock_code
    username = session_state.get("current_user", "anonymous")

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

    # MoE结果
    moe = session_state.get("moe_results", {})
    moe_data = None
    if moe.get("done"):
        moe_data = {
            "roles": dict(moe.get("roles", {})),
            "ceo": moe.get("ceo", ""),
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
        "analyses": {k: analyses[k] for k in done_keys},
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

        # 追加索引行 (轻量元数据, 方便 pandas 快速加载)
        index_entry = {
            "file": filename,
            "ts": record["archive_ts"],
            "date": record["archive_date"],
            "username": username,
            "model": record["model"],
            "stock_code": stock_code,
            "stock_name": stock_name,
            "close": price_snapshot.get("close", 0),
            "pe_ttm": info.get("市盈率TTM", ""),
            "pb": info.get("市净率PB", ""),
            "analyses_done": done_keys,
            "has_moe": moe_data is not None,
        }
        with open(INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")


def load_index():
    """加载索引为 pandas DataFrame, 用于回测筛选"""
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
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def load_archive(filename: str) -> dict:
    """加载单个归档文件的完整内容"""
    path = ARCHIVE_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_archive_stats() -> dict:
    """归档统计信息"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = list(ARCHIVE_DIR.glob("*.json"))
    # 排除非归档文件
    files = [f for f in files if f.name != "_index.jsonl"]
    total_size = sum(f.stat().st_size for f in files) if files else 0
    return {
        "count": len(files),
        "size_mb": round(total_size / 1024 / 1024, 2),
    }
