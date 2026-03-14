"""价值投机雷达 — 四维评分 + 综合买入信号"""

import re
import pandas as pd


def compute_signal(session_state: dict) -> dict | None:
    """
    基于已完成的分析结果，计算四维评分。
    返回 {"fundamental": 0-100, "catalyst": 0-100, "technical": 0-100,
           "capital": 0-100, "verdict": str, "resonance": bool}
    如果数据不足则返回 None。
    """
    analyses = session_state.get("analyses", {})
    moe = session_state.get("moe_results", {})

    # 至少需要三项分析完成
    if not all(analyses.get(k) for k in ["expectation", "trend", "fundamentals"]):
        return None

    info = session_state.get("stock_info", {})
    df = session_state.get("price_df", pd.DataFrame())

    # ── 1. 基本面强度 (0-100) ──────────────────────────────────
    fundamental = _score_fundamental(analyses["fundamentals"], info)

    # ── 2. 题材正宗度 (0-100) ──────────────────────────────────
    catalyst = _score_catalyst(analyses["expectation"])

    # ── 3. 技术启动度 (0-100) ──────────────────────────────────
    technical = _score_technical(analyses["trend"], df)

    # ── 4. 资金关注度 (0-100) ──────────────────────────────────
    capital = _score_capital(analyses["trend"], session_state)

    # ── 综合判断 ───────────────────────────────────────────────
    scores = [fundamental, catalyst, technical, capital]
    avg = sum(scores) / 4
    resonance = all(s >= 70 for s in scores)

    if resonance:
        verdict = "四维共振 — 强烈关注"
    elif avg >= 75:
        verdict = "综合优秀 — 值得关注"
    elif avg >= 60:
        verdict = "部分达标 — 择机介入"
    elif avg >= 45:
        verdict = "信号偏弱 — 观望为主"
    else:
        verdict = "条件不足 — 暂时回避"

    return {
        "fundamental": fundamental,
        "catalyst": catalyst,
        "technical": technical,
        "capital": capital,
        "avg": round(avg, 1),
        "verdict": verdict,
        "resonance": resonance,
    }


def _score_fundamental(text: str, info: dict) -> int:
    """从基本面分析文本 + 估值数据中提取评分"""
    score = 50  # 基准分

    # 从AI文本中提取评分（如 "综合评分：7/10" 或 "财务健康评分：8 / 10"）
    m = re.search(r"(?:综合评分|财务健康评分)[：:]\s*(\d+(?:\.\d+)?)\s*/\s*10", text)
    if m:
        ai_score = float(m.group(1))
        score = int(ai_score * 10)  # 转换到0-100

    # 通过/不通过信号
    if "✅" in text and "通过" in text:
        score = max(score, 65)
    if "❌" in text and "不通过" in text:
        score = min(score, 35)

    # PE估值加分/减分
    try:
        pe = float(info.get("市盈率TTM", 0))
        if 0 < pe < 20:
            score += 10
        elif 0 < pe < 30:
            score += 5
        elif pe > 80:
            score -= 10
    except (ValueError, TypeError):
        pass

    # 关键词信号
    positive_keywords = ["ROE.*1[5-9]|2[0-9]|3[0-9]", "持续增长", "现金流健康",
                        "护城河", "行业龙头", "低估"]
    negative_keywords = ["高负债", "现金流恶化", "业绩下滑", "商誉减值",
                        "财务造假", "ST"]

    for kw in positive_keywords:
        if re.search(kw, text):
            score += 5
    for kw in negative_keywords:
        if re.search(kw, text):
            score -= 8

    return max(0, min(100, score))


def _score_catalyst(text: str) -> int:
    """从预期差分析中提取题材正宗度评分"""
    score = 50

    # 超预期信号
    positive_count = len(re.findall(r"🟢|超预期|正向惊喜|催化", text))
    negative_count = len(re.findall(r"🔴|低预期|负向惊喜|风险", text))

    score += positive_count * 5
    score -= negative_count * 4

    # 炒作逻辑强度
    if re.search(r"核心叙事.*(?:业绩拐点|政策催化|产业趋势|国产替代|AI|新能源)", text):
        score += 10
    if re.search(r"逻辑.*(?:强|持续|明确|扎实)", text):
        score += 8
    if re.search(r"逻辑.*(?:弱|不确定|短暂|蹭概念)", text):
        score -= 10

    # 乐观情景概率
    m = re.search(r"乐观.*?(\d{2,3})%", text)
    if m:
        opt_prob = int(m.group(1))
        if opt_prob >= 40:
            score += 8
        elif opt_prob >= 30:
            score += 4

    # 催化事件密度
    event_count = len(re.findall(r"\d{4}年\d{1,2}月", text))
    if event_count >= 3:
        score += 8
    elif event_count >= 1:
        score += 4

    return max(0, min(100, score))


def _score_technical(text: str, df: pd.DataFrame) -> int:
    """从趋势分析 + K线数据中提取技术启动度评分"""
    score = 50

    # 从K线数据计算硬指标
    if not df.empty and len(df) >= 60:
        closes = df["收盘"].values
        ma5 = pd.Series(closes).rolling(5).mean().iloc[-1]
        ma20 = pd.Series(closes).rolling(20).mean().iloc[-1]
        ma60 = pd.Series(closes).rolling(60).mean().iloc[-1]

        # 均线多头排列
        if ma5 > ma20 > ma60:
            score += 15
        elif ma5 < ma20 < ma60:
            score -= 15

        # 近5日放量
        vols = df["成交量"].values
        if len(vols) >= 10:
            recent_vol = vols[-5:].mean()
            prev_vol = vols[-10:-5].mean()
            if prev_vol > 0 and recent_vol / prev_vol > 1.3:
                score += 10
            elif prev_vol > 0 and recent_vol / prev_vol < 0.7:
                score -= 5

        # 股价在MA20上方
        if closes[-1] > ma20:
            score += 5
        else:
            score -= 5

    # AI文本信号
    if re.search(r"看多|上涨|突破|放量上攻|启动", text):
        score += 8
    if re.search(r"看空|下跌|破位|缩量|下行", text):
        score -= 8
    if re.search(r"多头排列", text):
        score += 5
    if re.search(r"空头排列", text):
        score -= 5
    if re.search(r"金叉", text):
        score += 5
    if re.search(r"死叉", text):
        score -= 5

    return max(0, min(100, score))


def _score_capital(text: str, session_state: dict) -> int:
    """从趋势分析文本 + 资金数据中提取资金关注度评分"""
    score = 50

    # AI文本信号
    if re.search(r"主力.*(?:净流入|加仓|买入|吸筹|建仓)", text):
        score += 12
    if re.search(r"主力.*(?:净流出|减仓|卖出|出货|派发)", text):
        score -= 12
    if re.search(r"龙虎榜.*(?:买入|机构|知名游资)", text):
        score += 8

    # 北向资金信号
    nb = session_state.get("stock_northbound", "")
    if nb and "暂无" not in nb and "不可用" not in nb:
        if re.search(r"增持|加仓", nb):
            score += 10
        elif re.search(r"减持", nb):
            score -= 8
        else:
            score += 3  # 有北向数据本身就是关注信号

    # 融资融券信号
    margin = session_state.get("stock_margin", "")
    if margin and "暂无" not in margin and "不可用" not in margin:
        score += 3  # 有数据说明是两融标的

    return max(0, min(100, score))
