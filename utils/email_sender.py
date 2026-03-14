"""邮件发送 — 将个股分析报告推送到用户邮箱"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
import streamlit as st


def _get_smtp_config() -> tuple[str, int, str, str]:
    return (
        st.secrets.get("SMTP_HOST", ""),
        int(st.secrets.get("SMTP_PORT", 465)),
        st.secrets.get("SMTP_USER", ""),
        st.secrets.get("SMTP_PASS", ""),
    )


def smtp_configured() -> bool:
    host, _, user, pwd = _get_smtp_config()
    return bool(host and user and pwd)


def _md_to_html_simple(md: str) -> str:
    """简易 markdown → HTML（标题、加粗、列表、换行）"""
    import re
    html = md
    # 标题
    html = re.sub(r'^#{4}\s+(.+)$', r'<h4 style="color:#4f46e5;margin:12px 0 6px;">\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^#{3}\s+(.+)$', r'<h3 style="color:#1e1b4b;margin:14px 0 8px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^#{2}\s+(.+)$', r'<h2 style="color:#1e1b4b;margin:16px 0 8px;">\1</h2>', html, flags=re.MULTILINE)
    # 加粗
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    # 无序列表
    html = re.sub(r'^[-*]\s+(.+)$', r'<li style="margin:2px 0;">\1</li>', html, flags=re.MULTILINE)
    # 换行
    html = html.replace('\n', '<br>\n')
    return html


def build_report_html(stock_name: str, stock_code: str, info: dict,
                      analyses: dict, moe_results: dict,
                      model_name: str = "") -> str:
    """构建个股分析报告 HTML 邮件"""
    today_str = date.today().strftime("%Y-%m-%d")

    # 指标卡片
    metrics = [
        ("最新价", info.get("最新价(元)", "—")),
        ("市盈率TTM", info.get("市盈率TTM", "—")),
        ("市净率PB", info.get("市净率PB", "—")),
        ("换手率", info.get("换手率(%)", "—")),
        ("行业", info.get("行业", "—")),
    ]
    metrics_html = " &nbsp;|&nbsp; ".join(
        [f"<strong>{k}</strong>: {v}" for k, v in metrics if str(v) != "—"]
    )

    # 各项分析
    section_map = [
        ("expectation", "🔍 预期差分析"),
        ("trend", "📈 K线趋势研判"),
        ("fundamentals", "📋 基本面分析"),
        ("sentiment", "📣 舆情情绪分析"),
        ("sector", "🏭 板块联动分析"),
        ("holders", "👥 股东/机构动向"),
    ]

    sections_html = ""
    for key, title in section_map:
        content = analyses.get(key, "")
        if content:
            sections_html += f"""
            <div style="background:#fff;border-radius:12px;padding:16px;margin:12px 0;
                        border-left:4px solid #6366f1;">
                <h3 style="margin:0 0 8px;color:#1e1b4b;">{title}</h3>
                <div style="font-size:13px;color:#374151;line-height:1.7;">
                    {_md_to_html_simple(content)}
                </div>
            </div>"""

    # MoE 辩论结果
    moe_html = ""
    if moe_results and moe_results.get("done"):
        from analysis.moe import MOE_ROLES
        role_colors = {
            "trader": "#ef4444", "institution": "#3b82f6", "quant": "#8b5cf6",
            "value_spec": "#f59e0b", "retail": "#22c55e",
        }
        roles_html = ""
        for role in MOE_ROLES:
            text = moe_results.get("roles", {}).get(role["key"], "")
            if text:
                color = role_colors.get(role["key"], "#6b7280")
                roles_html += f"""
                <div style="border-left:3px solid {color};padding:8px 12px;margin:6px 0;
                            background:#fafafa;border-radius:0 8px 8px 0;">
                    <div style="font-weight:700;font-size:12px;color:{color};">{role['badge']}</div>
                    <div style="font-size:12px;color:#374151;margin-top:4px;">{text}</div>
                </div>"""

        ceo_text = moe_results.get("ceo", "")
        moe_html = f"""
        <div style="background:#fff;border-radius:12px;padding:16px;margin:12px 0;
                    border-left:4px solid #f59e0b;">
            <h3 style="margin:0 0 8px;color:#1e1b4b;">🎯 MoE 多角色辩论</h3>
            {roles_html}
            <div style="border:2px solid #f59e0b;border-radius:8px;padding:12px;margin-top:10px;
                        background:#fffbeb;">
                <div style="font-weight:800;color:#92400e;margin-bottom:6px;">👔 首席执行官 · 最终裁决</div>
                <div style="font-size:13px;color:#374151;line-height:1.7;">
                    {_md_to_html_simple(ceo_text)}
                </div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Microsoft YaHei','Helvetica Neue',sans-serif;max-width:680px;
             margin:0 auto;padding:20px;background:#f6f8ff;">

<div style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;
    border-radius:16px;padding:20px;text-align:center;">
    <h1 style="margin:0;font-size:22px;">📈 {stock_name} 深度分析报告</h1>
    <p style="margin:4px 0 0;opacity:0.9;">{today_str} | {stock_code} | 模型：{model_name}</p>
</div>

<div style="background:#fff;border-radius:12px;padding:14px;margin:12px 0;
            font-size:13px;color:#374151;text-align:center;">
    {metrics_html}
</div>

{sections_html}
{moe_html}

<div style="text-align:center;color:#9ca3af;font-size:11px;margin-top:20px;">
    ⚠️ 本报告仅供学习研究，不构成投资建议。<br>
    Generated by 呆瓜方后援会专属投研助手 · 立花道雪
</div>
</body></html>"""


def send_analysis_email(recipient: str, stock_name: str, stock_code: str,
                        info: dict, analyses: dict, moe_results: dict,
                        model_name: str = "") -> tuple[bool, str]:
    """发送个股分析报告邮件"""
    host, port, user, pwd = _get_smtp_config()
    if not host or not user or not pwd:
        return False, "SMTP 未配置，请在 Secrets 中添加 SMTP_HOST/SMTP_USER/SMTP_PASS"

    today_str = date.today().strftime("%Y-%m-%d")
    subject = f"📈 {stock_name} 深度分析报告 — {today_str}"

    html_body = build_report_html(stock_name, stock_code, info,
                                   analyses, moe_results, model_name)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, pwd)
                server.sendmail(user, recipient, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, pwd)
                server.sendmail(user, recipient, msg.as_string())
        return True, "发送成功"
    except Exception as e:
        return False, f"发送失败：{e}"
