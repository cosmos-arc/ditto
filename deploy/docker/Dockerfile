# ═══════════════════════════════════════════════════════════════════════
# Ditto Docker Image - Single-stage with Pixi
# ═══════════════════════════════════════════════════════════════════════
#
# 构建命令: docker build -t ditto:latest -f deploy/docker/Dockerfile .
# 运行命令: docker run -p 8000:8000 ditto:latest

FROM ghcr.io/prefix-dev/pixi:latest

WORKDIR /app

# 复制依赖定义文件（利用 Docker 缓存）
COPY pixi.toml pixi.lock pyproject.toml ./

# 安装生产依赖（不含 dev feature）
RUN pixi install --frozen --environment default

# 复制项目代码
COPY packages/ ./packages/
COPY config/ ./config/

# 创建必要目录
RUN mkdir -p /app/data /app/logs /app/prefect

# 环境变量默认值（可被 docker-compose 覆盖）
ENV DITTO_DATA_DIR=/app/data \
    ENVIRONMENT=production \
    PYTHONUNBUFFERED=1

# 健康检查（默认为 API）
# Note: Use Python instead of curl since base image may not include curl
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# 默认入口（API 服务）
CMD ["pixi", "run", "server"]
