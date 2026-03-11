"""Prompt 构建器 — 预期差、趋势、基本面"""

import json
from datetime import datetime, timedelta
from data.tushare_client import to_code6


def build_expectation_prompt(name, ts_code, info) -> tuple[str, str]:
    """构建预期差分析 prompt，返回 (prompt, system)"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    future_start = datetime.now().strftime("%Y年%m月")
    future_end = (datetime.now() + timedelta(days=90)).strftime("%Y年%m月")
    info_str = json.dumps({k: v for k, v in info.items()}, ensure_ascii=False)[:1400]

    system = (f"你是中国顶级买方研究院首席分析师，专精A股预期差挖掘与市场博弈分析。"
              f"⚠️ 今天的日期是 {today_str}。你的所有分析、时间判断、事件日历都必须以这个日期为锚点。"
              f"严禁出现任何早于今天日期的「未来」事件。")

    prompt = f"""## 分析标的：{name}（{to_code6(ts_code)}）
## 当前日期：{today_str}

## 公司基本信息
{info_str}

---
⚠️ 重要提示：本系统不提供新闻数据，你需要通过联网搜索功能，主动搜索 {name} 最近1个月内的最新新闻、公告、研报、政策动态。
请确保你的分析基于最新信息，而非过时数据。

请结合搜索到的最新信息，进行深度预期差分析（输出中文）：

### 一、当前核心炒作逻辑
详述当前市场炒作该股的核心叙事——是主题/概念驱动、业绩拐点、政策催化，还是资金博弈？逻辑强度与可持续性如何？

### 二、市场一致预期
目前市场对这只股的主流预期是什么？预期是否已经充分price in？

### 三、预期差所在（核心价值）
**🟢 超预期方向（潜在正向惊喜）：**
- （列出2-3个可能超出市场预期的具体因素）

**🔴 低预期风险（潜在负向惊喜）：**
- （列出1-2个可能不及预期的风险因素）

### 四、近期催化事件日历（{future_start} ~ {future_end}）
⚠️ 所有日期必须晚于 {today_str}，严禁出现过去的日期。如果某事件时间不确定，请写"待定"。
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
    return prompt, system


def build_trend_prompt(name, ts_code, price_smry, capital, dragon) -> tuple[str, str]:
    """构建趋势分析 prompt，返回 (prompt, system)"""
    system = "你是资深A股技术分析师，深谙量价关系、主力行为与资金博弈。"
    prompt = f"""## 分析标的：{name}（{to_code6(ts_code)}）

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
    return prompt, system


def build_fundamentals_prompt(name, ts_code, info, financial) -> tuple[str, str]:
    """构建基本面分析 prompt，返回 (prompt, system)"""
    system = "你是专业A股基本面研究员，精通财务分析与估值体系。"
    info_str = json.dumps({k: v for k, v in info.items()}, ensure_ascii=False)[:1000]
    prompt = f"""## 分析标的：{name}（{to_code6(ts_code)}）

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
    return prompt, system
