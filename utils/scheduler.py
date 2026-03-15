"""定时调度 — 每晚 22:00 北京时间自动运行深度 Top10 分析"""

import logging
import threading
import time as _time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_scheduler_thread = None
_scheduler_started = False

# 北京时间 UTC+8
_BJ_TZ = timezone(timedelta(hours=8))

# 默认模型（debug 阶段用 Mini，后续切换）
DEFAULT_MODEL = "🟤 豆包 · Seed 2.0 Mini"


def _now_bj() -> datetime:
    return datetime.now(_BJ_TZ)


def _is_trading_day(dt: datetime) -> bool:
    """判断是否为 A 股交易日（简易版：周一到周五，不含节假日）
    TODO: 后续可接入 Tushare trade_cal 精确判断
    """
    # 周末直接排除
    if dt.weekday() >= 5:
        return False

    # 尝试用 Tushare 交易日历精确判断
    try:
        from data.tushare_client import get_pro
        pro = get_pro()
        if pro:
            date_str = dt.strftime("%Y%m%d")
            cal = pro.trade_cal(
                exchange="SSE",
                start_date=date_str,
                end_date=date_str,
                fields="cal_date,is_open",
            )
            if cal is not None and not cal.empty:
                return bool(cal.iloc[0]["is_open"])
    except Exception as e:
        logger.debug("[scheduler] 交易日历查询失败: %s，回退到工作日判断", e)

    # 回退：工作日 = 交易日
    return True


def _scheduler_loop():
    """后台循环：每晚 22:00 北京时间触发深度分析"""
    while True:
        now = _now_bj()

        # 计算到下一个 22:00 的等待时间
        target = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(
            "[scheduler] 下次触发: %s（%.1f 小时后）",
            target.strftime("%Y-%m-%d %H:%M"), wait_seconds / 3600,
        )
        _time.sleep(wait_seconds)

        # 到达 22:00，检查是否交易日
        today_bj = _now_bj()
        if not _is_trading_day(today_bj):
            logger.info("[scheduler] 今日非交易日，跳过")
            continue

        # 检查是否已有今日缓存（避免多进程重复运行）
        from top10.deep_runner import get_deep_status, is_deep_running
        status = get_deep_status()
        if status and status.get("status") in ("done", "running"):
            logger.info("[scheduler] 今日深度分析已完成或正在运行，跳过")
            continue
        if is_deep_running():
            logger.info("[scheduler] 深度分析正在运行中，跳过")
            continue

        # 启动深度分析
        logger.info("[scheduler] 🚀 触发每日深度 Top10 分析...")
        try:
            from top10.deep_runner import run_deep_top10
            run_deep_top10(
                model_name=DEFAULT_MODEL,
                candidate_count=100,
                username="auto_scheduler",
            )
        except Exception as e:
            logger.error("[scheduler] 深度分析异常: %s", e, exc_info=True)


def start_top10_scheduler():
    """启动 Top10 定时调度器（仅启动一次）"""
    global _scheduler_thread, _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    logger.info("[scheduler] Top10 定时调度器已启动（每晚 22:00 北京时间）")
