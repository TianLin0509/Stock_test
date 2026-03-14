"""当日分析共享缓存 — 亲友间共享分析结果，节省 Token"""

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "shared_cache"


def _today_dir() -> Path:
    d = CACHE_DIR / date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(stock_code: str, model_name: str) -> str:
    """生成缓存文件名（去除 emoji 和特殊字符）"""
    safe_model = "".join(c for c in model_name if c.isalnum() or c in "._-")
    return f"{stock_code}_{safe_model}.json"


def save_shared(stock_code: str, stock_name: str, model_name: str,
                username: str, analyses: dict, moe_results: dict = None,
                stock_info: dict = None):
    """保存分析结果到共享缓存"""
    if not analyses:
        return
    # 至少有一项有效分析
    valid = {k: v for k, v in analyses.items() if v and len(v) > 100}
    if not valid:
        return

    cache_file = _today_dir() / _cache_key(stock_code, model_name)
    data = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "model_name": model_name,
        "username": username,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "analyses": valid,
        "moe_results": moe_results if moe_results and moe_results.get("done") else None,
        "stock_info": stock_info,
    }
    try:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception as e:
        logger.debug("[save_shared] 写入缓存失败: %s", e)


def find_shared(stock_code: str, exclude_user: str = "") -> list[dict]:
    """查找今日该股票的所有共享缓存（排除当前用户自己的）
    返回 [{model_name, username, timestamp, analyses_keys, file_path}, ...]
    """
    today = _today_dir()
    results = []
    if not today.exists():
        return results

    prefix = f"{stock_code}_"
    for f in today.iterdir():
        if not f.name.startswith(prefix) or not f.name.endswith(".json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if exclude_user and data.get("username") == exclude_user:
                continue
            results.append({
                "model_name": data.get("model_name", ""),
                "username": data.get("username", ""),
                "timestamp": data.get("timestamp", ""),
                "analyses_keys": list(data.get("analyses", {}).keys()),
                "has_moe": bool(data.get("moe_results")),
                "file_path": str(f),
            })
        except Exception as e:
            logger.debug("[find_shared] 读取缓存文件失败: %s", e)
            continue

    # 按时间倒排
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results


def load_shared(file_path: str) -> dict | None:
    """加载共享缓存的完整数据"""
    try:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("[load_shared] 加载失败: %s", e)
        return None


def cleanup_old(keep_days: int = 7):
    """清理过期缓存"""
    if not CACHE_DIR.exists():
        return
    cutoff = date.today().toordinal() - keep_days
    for d in CACHE_DIR.iterdir():
        if not d.is_dir():
            continue
        try:
            dir_date = date.fromisoformat(d.name)
            if dir_date.toordinal() < cutoff:
                import shutil
                shutil.rmtree(d, ignore_errors=True)
        except (ValueError, OSError):
            pass
