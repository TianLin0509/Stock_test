"""
智能上下文摘要构建器
用于 MoE 辩论和自由提问等需要引用已有分析结果的场景
不做硬切片，而是按段落结构提取关键结论
"""


def _extract_conclusions(text: str, max_lines: int = 15) -> str:
    """
    从分析文本中智能提取结论性内容
    优先保留：标题行、结论段、评分行、表格行
    """
    if not text:
        return ""

    lines = text.strip().split("\n")
    kept = []

    # 高优先级关键词——包含这些的行一定保留
    priority_keywords = [
        "结论", "评分", "评级", "裁决", "判断", "建议", "目标价",
        "止损", "支撑", "压力", "置信度", "核心",
        "乐观", "中性", "悲观", "通过", "不通过", "谨慎",
        "看多", "看空", "震荡", "买入", "减持", "回避",
        "预期差", "超预期", "低预期", "催化",
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 标题行（### 或 ** 开头）
        is_heading = stripped.startswith("#") or stripped.startswith("**")
        # 表格行
        is_table = "|" in stripped and stripped.count("|") >= 2
        # 包含关键词
        is_priority = any(kw in stripped for kw in priority_keywords)

        if is_heading or is_table or is_priority:
            kept.append(stripped)

        if len(kept) >= max_lines:
            break

    # 如果提取太少，回退到取前 N 行 + 后 N 行
    if len(kept) < 5 and len(lines) > 10:
        kept = [l.strip() for l in lines[:5] if l.strip()]
        kept.append("...")
        kept += [l.strip() for l in lines[-5:] if l.strip()]

    return "\n".join(kept)


def build_analysis_context(analyses: dict, max_per_module: int = 15) -> str:
    """
    将三个分析模块的结果构建为结构化上下文摘要
    按模块提取关键结论，不做硬切片
    """
    parts = []

    module_map = {
        "expectation":   "预期差分析",
        "trend":         "趋势研判",
        "fundamentals":  "基本面剖析",
    }

    for key, label in module_map.items():
        text = analyses.get(key, "")
        if not text or text.startswith("⚠️"):
            continue
        summary = _extract_conclusions(text, max_lines=max_per_module)
        if summary:
            parts.append(f"【{label}摘要】\n{summary}")

    return "\n\n".join(parts) if parts else "暂无已完成的分析结果"
