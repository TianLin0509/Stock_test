"""后台分析调度 — 数据增强 + 并行评分"""

import json
import logging
import os
import threading
from datetime import date
import pandas as pd
import streamlit as st
from ai.client import get_ai_client, call_ai, get_token_usage
from top10.prompts import SYSTEM_SUMMARY, build_summary_prompt
from top10.scorer import score_all

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# 持久化缓存（session_state + JSON 文件双重保险）
# ══════════════════════════════════════════════════════════════════════════════

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_key(model_name: str) -> str:
    return f"top10_result_{date.today().isoformat()}_{model_name}"


def _summary_key(model_name: str) -> str:
    return f"top10_summary_{date.today().isoformat()}_{model_name}"


def _file_path(model_name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{date.today().isoformat()}_{model_name}.json")


def _lock_path(model_name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{date.today().isoformat()}_{model_name}.lock")


def _acquire_lock(model_name: str, username: str) -> bool:
    """跨 session 文件锁：防止多用户同时触发分析。
    返回 True 表示拿到锁，False 表示已有人在分析。"""
    lp = _lock_path(model_name)
    try:
        # 检查是否存在未过期的锁（超过 15 分钟视为僵尸锁，自动清理）
        if os.path.exists(lp):
            import time as _time
            age = _time.time() - os.path.getmtime(lp)
            if age < 900:  # 15 分钟内
                return False
            # 僵尸锁，清理
            logger.warning("[top10] 清理僵尸锁（%.0f秒前创建）", age)
        with open(lp, "w", encoding="utf-8") as f:
            json.dump({"user": username, "ts": date.today().isoformat()}, f)
        return True
    except Exception:
        return True  # 锁文件操作失败不应阻塞分析


def _release_lock(model_name: str):
    lp = _lock_path(model_name)
    try:
        if os.path.exists(lp):
            os.remove(lp)
    except Exception:
        pass


def is_locked(model_name: str) -> dict | None:
    """检查是否有其他用户正在分析，返回 {user} 或 None"""
    lp = _lock_path(model_name)
    if not os.path.exists(lp):
        return None
    try:
        import time as _time
        if _time.time() - os.path.getmtime(lp) >= 900:
            return None  # 僵尸锁不算
        with open(lp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _meta_key(model_name: str) -> str:
    return f"top10_meta_{date.today().isoformat()}_{model_name}"


def get_cached_result(model_name: str) -> pd.DataFrame | None:
    """优先读 session_state，否则读文件"""
    key = _cache_key(model_name)
    if key in st.session_state:
        return st.session_state[key]
    # 尝试读文件
    fp = _file_path(model_name)
    if os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            df = pd.DataFrame(data["results"])
            df.index = df.index + 1
            df.index.name = "推荐排名"
            st.session_state[key] = df
            skey = _summary_key(model_name)
            if "summary" in data:
                st.session_state[skey] = data["summary"]
            # 加载触发者元信息
            mkey = _meta_key(model_name)
            if "triggered_by" in data:
                st.session_state[mkey] = {
                    "user": data["triggered_by"],
                    "tokens": data.get("tokens_used", 0),
                }
            return df
        except Exception:
            pass
    return None


def get_cached_meta(model_name: str) -> dict | None:
    """获取今日分析的触发者信息 {user, tokens}"""
    mkey = _meta_key(model_name)
    if mkey in st.session_state:
        return st.session_state[mkey]
    # 触发文件读取（会同时加载 meta）
    get_cached_result(model_name)
    return st.session_state.get(mkey)


def get_cached_summary(model_name: str) -> str | None:
    skey = _summary_key(model_name)
    if skey in st.session_state:
        return st.session_state[skey]
    # 触发文件读取（会同时加载 summary）
    get_cached_result(model_name)
    return st.session_state.get(skey)


def save_cached_result(model_name: str, df: pd.DataFrame, summary: str = "",
                       triggered_by: str = "", tokens_used: int = 0):
    # session_state 写入（后台线程无上下文时跳过）
    try:
        st.session_state[_cache_key(model_name)] = df
        if summary:
            st.session_state[_summary_key(model_name)] = summary
        if triggered_by:
            st.session_state[_meta_key(model_name)] = {
                "user": triggered_by, "tokens": tokens_used,
            }
    except Exception:
        pass  # 后台线程无 Streamlit 上下文
    # 写入文件持久化
    try:
        # 只保存可序列化的列
        save_cols = [c for c in df.columns if c != "K线摘要"]
        data = {
            "results": df[save_cols].to_dict(orient="records"),
            "summary": summary,
            "model": model_name,
            "date": date.today().isoformat(),
            "triggered_by": triggered_by,
            "tokens_used": tokens_used,
        }
        with open(_file_path(model_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def get_all_cached_models() -> list[str]:
    """获取今日所有已缓存的模型名称"""
    today_str = date.today().isoformat()
    models = []
    for fn in os.listdir(_CACHE_DIR):
        if fn.startswith(today_str) and fn.endswith(".json"):
            model = fn[len(today_str) + 1:-5]  # 去掉日期前缀和.json
            models.append(model)
    return models


# ══════════════════════════════════════════════════════════════════════════════
# 后台任务管理
# ══════════════════════════════════════════════════════════════════════════════

def get_job(ss) -> dict:
    return ss.get("top10_bg_job", {})


def is_running(ss) -> bool:
    return get_job(ss).get("status") == "running"


def is_done(ss) -> bool:
    return get_job(ss).get("status") == "done"


def _send_top10_email(summary: str, scored_df: pd.DataFrame,
                      model_name: str, triggered_by: str, tokens_used: int):
    """分析完成后自动发送 Top10 报告邮件"""
    try:
        from utils.email_sender import smtp_configured, _get_smtp_config, _md_to_html_simple
        if not smtp_configured():
            logger.debug("[top10] SMTP 未配置，跳过邮件发送")
            return

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        RECIPIENT = "290045045@qq.com"
        today_str = date.today().strftime("%Y-%m-%d")
        subject = f"🏆 今日 Top10 推荐 — {today_str} | by {triggered_by}"

        # 构建股票列表 HTML
        top10 = scored_df.head(10)
        rows_html = ""
        for i, (_, r) in enumerate(top10.iterrows(), 1):
            change = r.get("涨跌幅", 0)
            change_color = "#ef4444" if change < 0 else "#22c55e"
            advice = r.get("短线建议", "—")
            advice_colors = {
                "强烈推荐": "#dc2626", "推荐": "#f59e0b",
                "观望": "#6b7280", "回避": "#9ca3af",
            }
            advice_color = advice_colors.get(advice, "#6b7280")
            rows_html += f"""
            <tr style="border-bottom:1px solid #e5e7eb;">
                <td style="padding:8px;text-align:center;font-weight:700;color:#6366f1;">{i}</td>
                <td style="padding:8px;">{r['股票名称']}<br><span style="color:#9ca3af;font-size:11px;">{r['代码']}</span></td>
                <td style="padding:8px;text-align:center;">{r.get('最新价','—')}</td>
                <td style="padding:8px;text-align:center;color:{change_color};">{change:+.2f}%</td>
                <td style="padding:8px;text-align:center;font-weight:700;color:#6366f1;">{r['综合评分']}/10</td>
                <td style="padding:8px;text-align:center;">{r.get('行业','—')}</td>
                <td style="padding:8px;text-align:center;"><span style="background:{advice_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{advice}</span></td>
            </tr>"""

        # 构建总结 HTML
        summary_html = _md_to_html_simple(summary) if summary else ""

        # Token 显示
        if tokens_used >= 10000:
            tokens_display = f"{tokens_used / 10000:.1f}万"
        else:
            tokens_display = f"{tokens_used:,}"

        html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Microsoft YaHei','Helvetica Neue',sans-serif;max-width:720px;
             margin:0 auto;padding:20px;background:#f6f8ff;">

<div style="background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;
    border-radius:16px;padding:20px;text-align:center;">
    <h1 style="margin:0;font-size:22px;">🏆 今日 Top10 推荐</h1>
    <p style="margin:4px 0 0;opacity:0.9;">{today_str} | 模型：{model_name}</p>
    <p style="margin:4px 0 0;opacity:0.8;font-size:13px;">分析来自 {triggered_by} 用户，共消耗 {tokens_display} token</p>
</div>

<div style="background:#fff;border-radius:12px;padding:16px;margin:12px 0;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="background:#f8f9ff;border-bottom:2px solid #6366f1;">
                <th style="padding:8px;">排名</th>
                <th style="padding:8px;">股票</th>
                <th style="padding:8px;">最新价</th>
                <th style="padding:8px;">涨跌幅</th>
                <th style="padding:8px;">评分</th>
                <th style="padding:8px;">行业</th>
                <th style="padding:8px;">建议</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
</div>

<div style="background:#fff;border-radius:12px;padding:16px;margin:12px 0;
            border-left:4px solid #6366f1;">
    <h3 style="margin:0 0 8px;color:#1e1b4b;">📝 每日总结</h3>
    <div style="font-size:13px;color:#374151;line-height:1.7;">{summary_html}</div>
</div>

<div style="text-align:center;color:#9ca3af;font-size:11px;margin-top:20px;">
    ⚠️ 本报告仅供学习研究，不构成投资建议。<br>
    Generated by 呆瓜方后援会专属投研助手 · 立花道雪
</div>
</body></html>"""

        host, port, user, pwd = _get_smtp_config()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = RECIPIENT
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, pwd)
                server.sendmail(user, RECIPIENT, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, pwd)
                server.sendmail(user, RECIPIENT, msg.as_string())

        logger.info("[top10] 📧 Top10 报告已发送至 %s", RECIPIENT)
    except Exception as e:
        logger.warning("[top10] 邮件发送失败: %s", e)


def start_scoring(ss, candidates_df: pd.DataFrame, model_name: str,
                  username: str = ""):
    """启动后台评分线程"""
    if is_running(ss):
        return

    # 跨 session 文件锁：防止多用户重复触发
    if not _acquire_lock(model_name, username):
        lock_info = is_locked(model_name)
        who = lock_info.get("user", "其他用户") if lock_info else "其他用户"
        ss["top10_bg_job"] = {
            "status": "done", "error": None,
            "progress": [f"⏳ {who} 正在分析中，请稍等片刻后刷新页面查看结果"],
            "result": None, "summary": None,
        }
        return

    client, cfg, err = get_ai_client(model_name)
    if err:
        _release_lock(model_name)
        ss["top10_bg_job"] = {"status": "done", "error": err, "progress": [f"❌ {err}"]}
        return

    # 记录分析开始前的 token 用量
    tokens_before = get_token_usage()["total"]
    min_expected = max(5, len(candidates_df) // 3)  # 最低完整性阈值

    job = {
        "status": "running",
        "progress": [],
        "error": None,
        "result": None,
        "summary": None,
        "model": model_name,
        "total": len(candidates_df),
        "current": 0,
        "triggered_by": username,
    }
    ss["top10_bg_job"] = job

    def _run():
        try:
            # Phase 1: 数据增强
            job["progress"].append("📊 正在从 Tushare 获取增强数据（PE/PB/K线）...")
            try:
                from top10.tushare_data import enrich_candidates, ts_ok
                if ts_ok():
                    enriched_df = enrich_candidates(
                        candidates_df,
                        progress_callback=lambda msg: job["progress"].append(f"  {msg}")
                    )
                    job["progress"].append(f"✅ 数据增强完成（行业/PE/PB/K线摘要）")
                else:
                    enriched_df = candidates_df
                    job["progress"].append("⚠️ Tushare 不可用，使用基础数据分析")
            except Exception as e:
                enriched_df = candidates_df
                job["progress"].append(f"⚠️ 数据增强失败({e})，使用基础数据")

            # Phase 2: 并行 AI 评分
            total = len(enriched_df)
            job["progress"].append(f"🤖 开始并行AI评分，共 {total} 只候选股（3路并发）...")

            def progress_cb(current, total, msg):
                job["current"] = current
                job["progress"].append(f"[{current}/{total}] {msg}")

            scored = score_all(client, cfg, enriched_df,
                               model_name=model_name,
                               progress_callback=progress_cb,
                               max_workers=3)

            job["progress"].append(f"✅ 评分完成！共评分 {len(scored)} 只股票")

            # 完整性校验：评分结果太少说明大面积失败，不缓存
            if len(scored) < min_expected:
                job["error"] = f"评分结果不完整（仅 {len(scored)}/{len(candidates_df)} 只），不缓存，请重试"
                job["progress"].append(f"⚠️ 评分结果不完整（{len(scored)}/{len(candidates_df)}），本次不缓存")
                job["result"] = scored  # 仍展示给当前用户
                job["status"] = "done"
                _release_lock(model_name)
                return

            job["result"] = scored

            # Phase 3: 生成总结报告
            job["progress"].append("📝 正在生成每日总结报告...")
            summary = ""
            try:
                top10 = scored.head(10)
                stock_lines = []
                for _, r in top10.iterrows():
                    line = (f"- {r['股票名称']}({r['代码']}) "
                            f"行业:{r.get('行业','未知')} "
                            f"综合评分{r['综合评分']}/10 "
                            f"短线建议:{r.get('短线建议','未知')}")
                    stock_lines.append(line)
                stocks_text = "\n".join(stock_lines)

                # 加入板块轮动信号
                try:
                    from top10.tushare_data import get_sector_rotation
                    sectors = get_sector_rotation()
                    if sectors.get("概念板块"):
                        stocks_text += "\n\n今日概念板块涨幅Top5：" + "、".join(sectors["概念板块"])
                    if sectors.get("行业板块"):
                        stocks_text += "\n今日行业板块涨幅Top5：" + "、".join(sectors["行业板块"])
                except Exception:
                    pass

                summary_prompt = build_summary_prompt(stocks_text, total)
                summary, s_err = call_ai(
                    client, cfg, summary_prompt,
                    system=SYSTEM_SUMMARY, max_tokens=4000
                )
                if s_err:
                    summary = f"总结生成失败：{s_err}"
            except Exception as se:
                summary = f"总结生成失败：{se}"

            # 计算本次分析消耗的 token
            tokens_after = get_token_usage()["total"]
            tokens_used = tokens_after - tokens_before

            job["summary"] = summary
            job["tokens_used"] = tokens_used
            job["progress"].append(f"✅ 全部完成！（消耗 {tokens_used:,} token）")
            job["status"] = "done"

            save_cached_result(model_name, scored, summary,
                               triggered_by=username, tokens_used=tokens_used)

            _release_lock(model_name)

            # Phase 4: 自动发送邮件
            job["progress"].append("📧 正在发送 Top10 报告邮件...")
            _send_top10_email(summary, scored, model_name, username, tokens_used)

        except Exception as e:
            _release_lock(model_name)
            job["error"] = str(e)
            job["progress"].append(f"❌ 分析出错：{e}")
            job["status"] = "done"

    t = threading.Thread(target=_run, daemon=True)
    t.start()
