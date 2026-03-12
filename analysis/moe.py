"""MoE 多角色辩论裁决 v2 — 智能摘要，不丢失关键结论"""

import time
import streamlit as st
from ai.client import call_ai
from ai.context import build_analysis_context
from data.tushare_client import to_code6

MOE_ROLES = [
    {"key": "trader", "css": "r-trader", "badge": "⚡ 短线游资 · 闪电刀",
     "system": "你是A股短线游资操盘手「闪电刀」，时间维度1-10交易日。"
               "核心：题材热度、情绪共振、技术突破、龙头效应。判断直接，止损果断。"
               "语言简练带游资嗅觉，用「动力足不足」「有没有持续性」「跟不跟」等行话。"},
    {"key": "institution", "css": "r-inst", "badge": "🏛️ 中线机构 · 稳健先生",
     "system": "你是头部公募基金经理「稳健先生」，时间维度1-6个月。"
               "核心：基本面景气度+估值安全边际+政策配合。语言专业理性，注重数据逻辑链。"},
    {"key": "quant", "css": "r-quant", "badge": "🤖 量化资金 · Alpha机器",
     "system": "你是A股量化多因子研究员「Alpha机器」。"
               "基于数据和统计规律，关注动量/价值/质量/情绪/资金流因子，善用概率表述。"},
    {"key": "retail", "css": "r-retail", "badge": "👥 普通散户 · 韭菜代表 ⚠️反向指标",
     "system": "你是典型A股散户「韭菜代表」，你的观点是重要的反向指标！"
               "追涨杀跌，高点乐观底部恐慌。口语化，带散户焦虑/贪婪/侥幸心理。"},
]

CEO_SYSTEM = (
    "你是掌管300亿私募的顶级CEO，历经2008/2015/2018三次A股大崩盘，20年投资经验。"
    "深知散户情绪是最可靠的反向指标。"
    "综合四位专家观点，给出明确、可操作、附具体价格的最终裁决。"
    "重点参考机构和量化的理性分析，逆向参考散户的情绪化判断。"
)


def run_moe(client, cfg, name, ts_code, analyses: dict) -> None:
    code6 = to_code6(ts_code)

    with st.status(f"🎯 MoE 多方辩论 · {name}", expanded=True) as status:
        st.write("📋 汇总预期差、趋势、基本面三项分析结果...")
        time.sleep(0.5)
        context = build_analysis_context(analyses, max_per_module=15)
        st.write("🏟️ 召集四方专家进入辩论会场...")
        time.sleep(0.5)

        role_results: dict[str, str] = {}
        ai_errors = []

        for i, role in enumerate(MOE_ROLES, 1):
            st.write(f"🎙️ [{i}/{len(MOE_ROLES)}] {role['badge']} 正在发表观点...")
            prompt = f"""辩论标的：{name}（{code6}）

## 分析背景
{context}

---
从你的角色视角给出明确判断，控制在250字以内：

**核心判断：** 看多/看空/中性/观望
**判断依据（3条，引用上方分析中的具体数据）：**
1.
2.
3.
**操作建议：**（具体操作+入场价+止损价+目标价）
**最大风险：**（1条，具体描述）

保持角色特色和语言风格。"""
            text, err = call_ai(client, cfg, prompt,
                                system=role["system"], max_tokens=800)
            if err:
                text = f"⚠️ 该角色分析失败：{err}"
                ai_errors.append(err)
            role_results[role["key"]] = text
            st.write(f"  ✓ {role['badge']} 观点已提交")
            time.sleep(0.3)

        st.write("👔 首席执行官正在综合四方观点，做最终裁决...")
        time.sleep(0.4)

        roles_text = "\n\n".join(
            f"【{r['badge']}】\n{role_results.get(r['key'], '')}"
            for r in MOE_ROLES
        )

        ceo_prompt = f"""标的：{name}（{code6}）

## 四位专家观点
{roles_text}

## 原始分析摘要
{context}

---
综合以上信息给出最终操作裁决。
⚠️ **散户（韭菜代表）的观点是反向指标，逆向参考。**

## 🎯 最终操作结论

**操作评级：** 强烈买入/买入/谨慎介入/持有观察/减持/回避

**裁决逻辑（3-4句，说明为什么这样判断）：**

**目标价体系：**
| 维度 | 价格 | 依据 |
|-----|-----|-----|
| 当前股价 | ___元 | — |
| 短线目标（1-2周）| | |
| 中线目标（1-3月）| | |
| 止损位 | | |

**仓位策略：** 建议仓位___%, 介入方式：___

**核心逻辑（2条）：**
1.
2.

**核心风险（2条）：**
1.
2.

**策略有效期：** ___个交易日，若___则策略失效。"""

        ceo_text, ceo_err = call_ai(client, cfg, ceo_prompt,
                                     system=CEO_SYSTEM, max_tokens=2000)

        if ceo_err:
            ceo_text = f"⚠️ CEO裁决生成失败：{ceo_err}\n\n建议切换其他模型后重新尝试。"
            status.update(label=f"⚠️ MoE 辩论完成（部分错误）", state="complete")
        else:
            status.update(label=f"✅ MoE 四方辩论裁决完成！", state="complete")

    st.session_state["moe_results"] = {
        "roles": role_results, "ceo": ceo_text, "done": True,
    }
