# A股智能投研助手 — Docker 部署镜像
FROM python:3.11-slim

# 系统依赖（pandas/numpy/tushare/akshare 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev gcc g++ libffi-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 确保运行时目录存在
RUN mkdir -p user_data data/archive data/shared_cache cache

# Streamlit 默认端口
EXPOSE 8501

# 健康检查（首次启动较慢，timeout 放宽）
HEALTHCHECK --interval=30s --timeout=30s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
