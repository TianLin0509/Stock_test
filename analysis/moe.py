"""MoE 多角色辩论裁决"""

import streamlit as st
from ai.client import call_ai
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

CEO_SYSTEM = ("你是掌管300亿私募的顶级CEO，历经2008/2015/2018三次A股大崩盘，20年投资经验。"
              "深知散户情绪是最可靠的反向指标。给出明确、可操作、附具体价格的最终裁决。")


def run_moe(client, cfg, name, ts_code, analyses: dict) -> None:
    code6 = to_code6(ts_code)
    summary = f"""分析摘要：{name}（{code6}）
【预期差】{analyses.get('expectation','')[:900]}
【趋势】{analyses.get('trend','')[:900]}
【基本面】{analyses.get('fundamentals','')[:900]}"""

    role_results: dict[str, str] = {}
    ai_errors = []

    for role in MOE_ROLES:
        with st.spinner(f"{role['badge']} 发表观点中..."):
            prompt = f"""辩论标的：{name}（{code6}）
背景：{summary[:2200]}
---
从你的角色视角给出明确判断，控制在220字以内：
**核心判断：** 看多/看空/中性/观望
**主要依据（3条）：**
1.
2.
3.
**操作建议：**（具体操作+参考点位）
**最大风险：**（1个）
保持角色特色和语言风格。"""
            text, err = call_ai(client, cfg, prompt,
                                system=role["system"], max_tokens=700)
        if err:
            text = f"⚠️ 该角色分析失败：{err}"
            ai_errors.append(err)
        role_results[role["key"]] = text
        st.markdown(f"""<div class="role-card {role['css']}">
  <div class="role-badge">{role['badge']}</div>
  <div class="role-content">{text}</div>
</div>""", unsafe_allow_html=True)

    if ai_errors:
        st.markdown(f'<div class="status-banner warn">⚠️ 部分角色调用失败，建议切换模型重试：{ai_errors[0]}</div>',
                    unsafe_allow_html=True)

    st.markdown("---")

    roles_text = "\n\n".join(f"【{r['badge']}】\n{role_results.get(r['key'],'')}"
                              for r in MOE_ROLES)
    with st.spinner("👔 首席执行官 综合裁决中..."):
        ceo_prompt = f"""标的：{name}（{code6}）
四位专家观点：{roles_text}
背景：{summary[:1200]}
---
给出最终操作裁决。**散户（韭菜代表）的观点是反向指标，逆向参考。**

## 🎯 最终操作结论
**操作评级：** 强烈买入/买入/谨慎介入/持有观察/减持/回避
**裁决逻辑（3-4句）：**
**目标价体系：**
| 维度 | 价格 | 依据 |
|-----|-----|-----|
| 当前股价 | X.XX元 | — |
| 短线目标（1-2周）| | |
| 中线目标（1-3月）| | |
| 止损位 | | |
**仓位策略：** 建议仓位X%，介入方式：
**核心逻辑（2条）：**
**核心风险（2条）：**
**策略有效期：** ___个交易日，若[条件]则失效。"""

        ceo_text, ceo_err = call_ai(client, cfg, ceo_prompt, system=CEO_SYSTEM, max_tokens=1600)

    if ceo_err:
        ceo_text = f"⚠️ CEO裁决生成失败：{ceo_err}\n\n建议切换其他模型后重新尝试。"

    st.markdown(f"""<div class="role-card r-ceo">
  <div class="role-badge">👔 首席执行官 · 最终裁决</div>
  <div class="role-content">{ceo_text}</div>
</div>""", unsafe_allow_html=True)

    st.session_state["moe_results"] = {
        "roles": role_results, "ceo": ceo_text, "done": True,
    }
