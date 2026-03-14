#!/bin/bash
# A股智能投研助手 — 火山引擎部署脚本
# 在服务器上执行：bash deploy.sh

set -e

echo "===== A股智能投研助手 部署 ====="

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "📦 安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker && systemctl start docker
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ docker compose 不可用，请升级 Docker 到最新版"
    exit 1
fi

# 2. 拉取代码（首次）或更新
REPO_URL="https://github.com/lintian-a/Stock_test.git"
APP_DIR="/opt/stock-research"

if [ -d "$APP_DIR" ]; then
    echo "🔄 更新代码..."
    cd "$APP_DIR"
    git pull
else
    echo "📥 克隆仓库..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. 检查 secrets.toml
if [ ! -f .streamlit/secrets.toml ]; then
    echo "⚠️  缺少 .streamlit/secrets.toml"
    echo "请手动创建后重新运行："
    echo "  mkdir -p .streamlit"
    echo "  nano .streamlit/secrets.toml"
    exit 1
fi

# 4. 确保 K线历史数据存在
if [ ! -d data/history ] || [ -z "$(ls data/history/*.parquet 2>/dev/null)" ]; then
    echo "⚠️  缺少 K线历史数据 data/history/*.parquet"
    echo "请从本地上传 3 个 parquet 文件到 $APP_DIR/data/history/"
    exit 1
fi

# 5. 确保持久化目录存在
mkdir -p user_data data/archive

# 6. 构建 & 启动
echo "🐳 构建 Docker 镜像..."
docker compose build

echo "🚀 启动服务..."
docker compose up -d

echo ""
echo "===== 部署完成 ====="
echo "🌐 访问地址：http://$(hostname -I | awk '{print $1}'):8501"
echo ""
echo "常用命令："
echo "  docker compose logs -f    # 查看日志"
echo "  docker compose restart    # 重启"
echo "  docker compose down       # 停止"
echo "  bash deploy.sh            # 更新部署"
