"""定时备份 — GitHub推送 + 邮件备份归档数据

每天12:00自动执行：
1. 将 data/archive/ 下所有文件推送到 GitHub 仓库的 data-archive 分支
2. 将当日新增归档打包发送到管理员邮箱
"""

import json
import base64
import threading
import time as _time
from datetime import datetime, date
from pathlib import Path

ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "archive"
ADMIN_EMAIL = "290045045@qq.com"

_backup_thread = None
_backup_started = False


def _get_github_config():
    """从 secrets 读取 GitHub 配置"""
    try:
        import streamlit as st
        return {
            "token": st.secrets.get("GITHUB_TOKEN", ""),
            "repo": st.secrets.get("GITHUB_REPO", "TianLin0509/Stock_test"),
            "branch": st.secrets.get("GITHUB_ARCHIVE_BRANCH", "data-archive"),
        }
    except Exception:
        return {"token": "", "repo": "", "branch": "data-archive"}


def push_to_github() -> tuple[bool, str]:
    """将归档文件推送到 GitHub data-archive 分支"""
    import requests

    cfg = _get_github_config()
    token = cfg["token"]
    repo = cfg["repo"]
    branch = cfg["branch"]

    if not token:
        return False, "GITHUB_TOKEN 未配置"

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = list(ARCHIVE_DIR.glob("*.json")) + list(ARCHIVE_DIR.glob("*.jsonl"))
    if not files:
        return True, "无归档文件需要推送"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    api = f"https://api.github.com/repos/{repo}"

    # 确保分支存在
    r = requests.get(f"{api}/branches/{branch}", headers=headers, timeout=15)
    if r.status_code == 404:
        # 获取 main 分支的 SHA 作为基础创建新分支
        r_main = requests.get(f"{api}/git/ref/heads/main", headers=headers, timeout=15)
        if r_main.status_code != 200:
            return False, f"无法获取 main 分支: {r_main.text[:200]}"
        sha = r_main.json()["object"]["sha"]
        r_create = requests.post(
            f"{api}/git/refs",
            headers=headers, timeout=15,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        if r_create.status_code not in (200, 201):
            return False, f"创建分支失败: {r_create.text[:200]}"

    # 逐文件推送（PUT contents API，自动处理创建/更新）
    pushed = 0
    errors = []
    for f in files:
        path_in_repo = f"data/archive/{f.name}"
        content_b64 = base64.b64encode(f.read_bytes()).decode()

        # 检查文件是否已存在（获取 SHA 用于更新）
        r_get = requests.get(
            f"{api}/contents/{path_in_repo}?ref={branch}",
            headers=headers, timeout=15,
        )
        payload = {
            "message": f"backup: {f.name}",
            "content": content_b64,
            "branch": branch,
        }
        if r_get.status_code == 200:
            existing_sha = r_get.json().get("sha", "")
            # 比较内容是否有变化
            existing_content = r_get.json().get("content", "").replace("\n", "")
            if existing_content == content_b64:
                continue  # 内容未变，跳过
            payload["sha"] = existing_sha

        r_put = requests.put(
            f"{api}/contents/{path_in_repo}",
            headers=headers, timeout=30,
            json=payload,
        )
        if r_put.status_code in (200, 201):
            pushed += 1
        else:
            errors.append(f"{f.name}: {r_put.status_code}")

        _time.sleep(0.5)  # 避免触发 GitHub API 限流

    msg = f"已推送 {pushed} 个文件到 {repo}:{branch}"
    if errors:
        msg += f"，{len(errors)} 个失败: {'; '.join(errors[:3])}"
    return len(errors) == 0, msg


def send_backup_email() -> tuple[bool, str]:
    """将当日新增归档打包发送到管理员邮箱"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication

    try:
        import streamlit as st
        host = st.secrets.get("SMTP_HOST", "")
        port = int(st.secrets.get("SMTP_PORT", 465))
        user = st.secrets.get("SMTP_USER", "")
        pwd = st.secrets.get("SMTP_PASS", "")
    except Exception:
        return False, "SMTP 未配置"

    if not host or not user or not pwd:
        return False, "SMTP 未配置"

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().strftime("%Y%m%d")

    # 找当日归档文件
    today_files = [f for f in ARCHIVE_DIR.glob("*.json")
                   if f.name.startswith(today_str)]

    if not today_files:
        return True, "今日无新增归档"

    # 构建邮件
    subject = f"📦 投研助手归档备份 — {date.today().strftime('%Y-%m-%d')} ({len(today_files)}条)"

    # 汇总信息
    summary_lines = []
    for f in sorted(today_files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            summary_lines.append(
                f"• {data.get('stock_name', '')}({data.get('stock_code', '')}) "
                f"by {data.get('username', '')} "
                f"[{', '.join(data.get('analyses_validated', []))}]"
            )
        except Exception:
            summary_lines.append(f"• {f.name}")

    body_text = f"今日共 {len(today_files)} 条分析归档：\n\n" + "\n".join(summary_lines)
    body_text += "\n\n详细内容见附件JSON文件。"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ADMIN_EMAIL
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # 附加每个归档文件（JSON）
    for f in today_files:
        att = MIMEApplication(f.read_bytes(), Name=f.name)
        att["Content-Disposition"] = f'attachment; filename="{f.name}"'
        msg.attach(att)

    # 也附加索引文件
    index_file = ARCHIVE_DIR / "_index.jsonl"
    if index_file.exists():
        att = MIMEApplication(index_file.read_bytes(), Name="_index.jsonl")
        att["Content-Disposition"] = 'attachment; filename="_index.jsonl"'
        msg.attach(att)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, pwd)
                server.sendmail(user, ADMIN_EMAIL, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, pwd)
                server.sendmail(user, ADMIN_EMAIL, msg.as_string())
        return True, f"已发送 {len(today_files)} 个归档到 {ADMIN_EMAIL}"
    except Exception as e:
        return False, f"邮件发送失败: {e}"


def run_daily_backup():
    """执行每日备份：GitHub + 邮件"""
    results = []

    ok1, msg1 = push_to_github()
    results.append(f"GitHub: {'✅' if ok1 else '❌'} {msg1}")

    ok2, msg2 = send_backup_email()
    results.append(f"邮件: {'✅' if ok2 else '❌'} {msg2}")

    # 记录备份日志
    log_file = ARCHIVE_DIR / "_backup_log.txt"
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] " +
                " | ".join(results) + "\n")

    return results


def _backup_scheduler():
    """后台线程：每天12:00执行备份"""
    while True:
        now = datetime.now()
        # 计算到下一个12:00的秒数
        target = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if now >= target:
            # 今天12:00已过，等明天
            from datetime import timedelta
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        _time.sleep(wait_seconds)

        # 执行备份
        try:
            run_daily_backup()
        except Exception:
            pass


def start_backup_scheduler():
    """启动备份调度器（仅启动一次）"""
    global _backup_thread, _backup_started
    if _backup_started:
        return
    _backup_started = True
    _backup_thread = threading.Thread(target=_backup_scheduler, daemon=True)
    _backup_thread.start()
