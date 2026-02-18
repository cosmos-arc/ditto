# Docker 部署实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Docker 部署配置，支持 2 容器架构（ditto-api + ditto-job）

**Architecture:** 基于 Pixi 的单阶段镜像构建，Bind Mount 持久化，环境变量注入配置

**Tech Stack:** Docker, Docker Compose, Pixi, Prefect, FastAPI

---

## 前置条件

- 设计文档: `docs/plans/2026-02-18-docker-deployment-design.md`
- 分支: `feat/docker-deployment`

---

## Task 1: 创建 .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: 创建 .dockerignore 文件**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
.eggs/
*.egg

# Virtual environments
.pixi/
venv/
.venv/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# Build artifacts
dist/
build/
*.whl

# Documentation
docs/_build/

# Local config (sensitive)
.env
.env.local
*.secret
.secrets/

# Git
.git/
.gitignore

# Docker
Dockerfile*
docker-compose*.yml
.docker/

# Development files
*.log
*.tmp
*.temp
logs/
data/

# OS
.DS_Store
Thumbs.db

# Pre-commit
.pre-commit-config.yaml
```

**Step 2: 提交**

```bash
git add .dockerignore
git commit -m "chore: 添加 .dockerignore 排除不必要文件"
```

---

## Task 2: 创建 Dockerfile

**Files:**
- Create: `deploy/docker/Dockerfile`

**Step 1: 创建 deploy/docker 目录**

```bash
mkdir -p deploy/docker
```

**Step 2: 创建 Dockerfile**

```dockerfile
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
COPY apps/ ./apps/
COPY config/ ./config/

# 创建必要目录
RUN mkdir -p /app/data /app/logs /app/prefect

# 环境变量默认值（可被 docker-compose 覆盖）
ENV DITTO_DATA_DIR=/app/data \
    ENVIRONMENT=production \
    PYTHONUNBUFFERED=1

# 健康检查（默认为 API）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# 默认入口（API 服务）
CMD ["pixi", "run", "server"]
```

**Step 3: 提交**

```bash
git add deploy/docker/Dockerfile
git commit -m "feat: 添加 Dockerfile（Pixi 单阶段构建）"
```

---

## Task 3: 创建 docker-compose.yml

**Files:**
- Create: `deploy/docker/docker-compose.yml`

**Step 1: 创建 docker-compose.yml**

```yaml
# ═══════════════════════════════════════════════════════════════════════
# Ditto Application Stack
# ═══════════════════════════════════════════════════════════════════════
#
# 启动: docker compose up -d
# 查看: docker compose logs -f
# 停止: docker compose down

services:
  # ───────────────────────────────────────────────────────────────────
  # API 服务
  # ───────────────────────────────────────────────────────────────────
  ditto-api:
    image: ditto:${DITTO_VERSION:-latest}
    container_name: ditto-api
    restart: unless-stopped
    build:
      context: ../..
      dockerfile: deploy/docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DITTO_DATA_DIR=/app/data
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_DIR=/app/logs
      - TUSHARE_TOKEN=${TUSHARE_TOKEN}
      - PREFECT_API_URL=http://ditto-job:4200/api
    volumes:
      - ${DITTO_DATA_PATH:-/opt/ditto/data}:/app/data
      - ${DITTO_LOGS_PATH:-/opt/ditto/logs}/api:/app/logs
    networks:
      - ditto-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 1G

  # ───────────────────────────────────────────────────────────────────
  # Job 服务 (Prefect Server + Worker)
  # ───────────────────────────────────────────────────────────────────
  ditto-job:
    image: ditto:${DITTO_VERSION:-latest}
    container_name: ditto-job
    restart: unless-stopped
    build:
      context: ../..
      dockerfile: deploy/docker/Dockerfile
    ports:
      - "4200:4200"
    environment:
      - DITTO_DATA_DIR=/app/data
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_DIR=/app/logs
      - TUSHARE_TOKEN=${TUSHARE_TOKEN}
      - PREFECT_HOME=/app/prefect
      - PREFECT_API_DATABASE_CONNECTION_URL=sqlite+aiosqlite:////app/prefect/prefect.db
    volumes:
      - ${DITTO_DATA_PATH:-/opt/ditto/data}:/app/data
      - ${DITTO_LOGS_PATH:-/opt/ditto/logs}/job:/app/logs
      - ${PREFECT_DATA_PATH:-/opt/ditto/prefect}:/app/prefect
    networks:
      - ditto-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4200/api/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 2G
    command: >
      sh -c "pixi run prefect server start --host 0.0.0.0 &
             sleep 5 &&
             pixi run prefect worker start --pool default"

networks:
  ditto-network:
    driver: bridge
```

**Step 2: 提交**

```bash
git add deploy/docker/docker-compose.yml
git commit -m "feat: 添加 docker-compose.yml（2 容器编排）"
```

---

## Task 4: 创建 .env.example

**Files:**
- Create: `deploy/docker/.env.example`

**Step 1: 创建 .env.example**

```bash
# ═══════════════════════════════════════════════════════════════════════
# Ditto Docker Environment Configuration
# ═══════════════════════════════════════════════════════════════════════
#
# 复制此文件为 .env.local 并填写实际值
# cp .env.example .env.local

# ───────────────────────────────────────────────────────────────────
# 镜像版本
# ───────────────────────────────────────────────────────────────────
DITTO_VERSION=latest

# ───────────────────────────────────────────────────────────────────
# 运行环境 (development / testing / production)
# ───────────────────────────────────────────────────────────────────
ENVIRONMENT=production

# ───────────────────────────────────────────────────────────────────
# 存储路径（主机目录）
# ───────────────────────────────────────────────────────────────────
DITTO_DATA_PATH=/opt/ditto/data
DITTO_LOGS_PATH=/opt/ditto/logs
PREFECT_DATA_PATH=/opt/ditto/prefect

# ───────────────────────────────────────────────────────────────────
# 敏感信息
# ───────────────────────────────────────────────────────────────────
# 请通过以下方式之一设置 TUSHARE_TOKEN：
# 1. 在此文件中设置（不要提交到 git）
# 2. 设置主机环境变量: export TUSHARE_TOKEN=xxx
# 3. 启动时传入: TUSHARE_TOKEN=xxx docker compose up -d
# TUSHARE_TOKEN=
```

**Step 2: 提交**

```bash
git add deploy/docker/.env.example
git commit -m "feat: 添加 .env.example 环境变量模板"
```

---

## Task 5: 创建部署说明 README.md

**Files:**
- Create: `deploy/docker/README.md`

**Step 1: 创建 README.md**

```markdown
# Ditto Docker 部署

本目录包含 Ditto 量化系统的 Docker 部署配置。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Host                             │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │   ditto-api     │  │   ditto-job                     │  │
│  │   FastAPI       │  │   Prefect Server + Worker       │  │
│  │   :8000         │  │   :4200                         │  │
│  └────────┬────────┘  └───────────────┬─────────────────┘  │
│           │                           │                     │
│           └─────────────┬─────────────┘                     │
│                         ▼                                   │
│           ┌──────────────────────────────┐                  │
│           │   /opt/ditto/                │                  │
│           │   ├── data/  (业务数据)      │                  │
│           │   ├── logs/  (日志)          │                  │
│           │   │   ├── api/               │                  │
│           │   │   └── job/               │                  │
│           │   └── prefect/ (Prefect DB)  │                  │
│           └──────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 创建数据目录

```bash
sudo mkdir -p /opt/ditto/{data,prefect,logs/api,logs/job}
```

### 2. 配置环境变量

```bash
cp .env.example .env.local
# 编辑 .env.local，设置 TUSHARE_TOKEN
```

### 3. 构建并启动

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose --env-file .env.local up -d
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/healthz
curl http://localhost:4200/api/health

# 查看日志
docker compose logs -f ditto-api
docker compose logs -f ditto-job
```

## 访问地址

| 服务 | 地址 |
|------|------|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Prefect UI | http://localhost:4200 |

## 日常运维

```bash
# 查看日志
docker compose logs -f ditto-api
docker compose logs -f ditto-job

# 重启服务
docker compose restart ditto-api
docker compose restart ditto-job

# 更新部署
git pull
docker compose build
docker compose up -d

# 停止服务
docker compose down
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DITTO_VERSION | 镜像版本 | latest |
| ENVIRONMENT | 运行环境 | production |
| DITTO_DATA_PATH | 数据目录 | /opt/ditto/data |
| DITTO_LOGS_PATH | 日志目录 | /opt/ditto/logs |
| PREFECT_DATA_PATH | Prefect 数据目录 | /opt/ditto/prefect |
| TUSHARE_TOKEN | Tushare API Token | (必须设置) |

## 资源配置

| 服务 | 内存限制 | 说明 |
|------|----------|------|
| ditto-api | 1GB | API 服务 |
| ditto-job | 2GB | Prefect Server + Worker |

## 故障排查

### 容器无法启动

```bash
# 查看容器日志
docker compose logs ditto-api
docker compose logs ditto-job

# 检查容器状态
docker compose ps
```

### 权限问题

```bash
# 确保 Docker 用户有权限访问 /opt/ditto
sudo chown -R $USER:$USER /opt/ditto
```

### 网络问题

```bash
# 检查网络连接
docker network ls
docker network inspect ditto-network
```

## 相关文档

- [设计文档](../../docs/plans/2026-02-18-docker-deployment-design.md)
- [Observability 部署](../observability/README.md)
```

**Step 2: 提交**

```bash
git add deploy/docker/README.md
git commit -m "docs: 添加 Docker 部署说明"
```

---

## Task 6: 支持 LOG_DIR 环境变量

**Files:**
- Modify: `apps/port/src/ditto_port/registry/infra/config.py:108-121`
- Test: `apps/port/tests/unit/registry/test_config_provider_unit.py`（如需要）

**Step 1: 修改 ConfigProvider 支持 LOG_DIR 环境变量**

在 `data_store_settings` 方法中添加 `LOG_DIR` 环境变量支持：

```python
@provide
def data_store_settings(self, config_loader: ConfigLoader) -> DataStoreSettings:
    """加载数据存储配置。"""
    values: dict[str, Any] = load_env_file(config_loader, "data_store")

    # 支持 CLI 透传的环境变量覆盖
    if override := os.getenv("DITTO_DATA_ROOT"):
        values["data_root"] = override
    if override := os.getenv("SQLITE_PATH"):
        values["sqlite_path"] = override
    if override := os.getenv("DUCKDB_PATH"):
        values["duckdb_path"] = override
    # 支持 LOG_DIR 环境变量（Docker 部署用）
    if override := os.getenv("LOG_DIR"):
        values["logs_path"] = override

    return DataStoreSettings.model_validate(values)
```

**Step 2: 修改 DataStoreSettings 支持可选的 logs_path**

在 `packages/datahub/src/ditto_datahub/config/data_store.py` 中添加 `logs_path` 字段：

```python
class DataStoreSettings(BaseModel):
    # ... 现有字段 ...

    # ========== 可选覆盖路径 ==========
    logs_path: Path | None = Field(default=None, description="日志路径覆盖")

    # ========== 解析后的路径 ==========

    @property
    def resolved_logs_path(self) -> Path:
        """解析后的日志路径。"""
        return self.logs_path or self.data_root / "logs"
```

然后更新 `logs_path` 属性为使用 `resolved_logs_path`。

**Step 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/config/data_store.py
git add apps/port/src/ditto_port/registry/infra/config.py
git commit -m "feat: 支持 LOG_DIR 环境变量覆盖日志路径"
```

---

## Task 7: 更新 Observability docker-compose.yml

**Files:**
- Modify: `deploy/observability/docker-compose.yml:52-53`

**Step 1: 更新 Vector 日志挂载路径**

将：
```yaml
volumes:
  - ../../logs:/logs:ro
```

改为：
```yaml
volumes:
  - ${DITTO_LOGS_PATH:-/opt/ditto/logs}:/logs:ro
```

**Step 2: 提交**

```bash
git add deploy/observability/docker-compose.yml
git commit -m "fix: 更新 Vector 日志挂载路径支持 DITTO_LOGS_PATH"
```

---

## Task 8: 更新 Vector 配置

**Files:**
- Modify: `deploy/observability/vector.toml`

**Step 1: 更新 Vector 配置支持分离的 api/job 日志**

```toml
# Vector 配置文件 - Ditto 可观测性系统
# 功能: 从应用日志文件采集日志并推送到 VictoriaLogs

# ============ 数据源 ============

# API 日志源
[sources.api_logs]
type = "file"
include = ["/logs/api/*.jsonl", "/logs/api/*.json"]
read_from = "end"

# Job 日志源
[sources.job_logs]
type = "file"
include = ["/logs/job/*.jsonl", "/logs/job/*.json"]
read_from = "end"

# 兼容旧格式（单一日志目录）
[sources.legacy_logs]
type = "file"
include = ["/logs/ditto*.jsonl"]
read_from = "end"

# ============ 数据转换 ============

# API 日志转换
[transforms.api_logs_transform]
type = "remap"
inputs = ["api_logs"]
source = '''
. = parse_json!(.message)
.source = "ditto-api"
'''

# Job 日志转换
[transforms.job_logs_transform]
type = "remap"
inputs = ["job_logs"]
source = '''
. = parse_json!(.message)
.source = "ditto-job"
'''

# 兼容旧格式转换
[transforms.legacy_logs_transform]
type = "remap"
inputs = ["legacy_logs"]
source = '''
. = parse_json!(.message)
'''

# ============ 数据汇 - VictoriaLogs ============

[sinks.victorialogs]
type = "http"
inputs = ["api_logs_transform", "job_logs_transform", "legacy_logs_transform"]
uri = "http://victorialogs:9428/insert/jsonline?_stream_fields=source"
encoding.codec = "json"
framing.method = "newline_delimited"
batch.max_events = 100

# ============ 健康检查 ============

[api]
enabled = true
address = "0.0.0.0:8686"
```

**Step 2: 提交**

```bash
git add deploy/observability/vector.toml
git commit -m "feat: 更新 Vector 配置支持分离的 api/job 日志"
```

---

## Task 9: 更新 .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: 添加 .env.local 到 .gitignore**

在 `.gitignore` 中添加：
```
# Docker 部署环境变量（敏感信息）
.env.local
deploy/docker/.env.local
```

**Step 2: 提交**

```bash
git add .gitignore
git commit -m "chore: 添加 .env.local 到 .gitignore"
```

---

## Task 10: 验证与清理

**Step 1: 运行检查**

```bash
pixi run -e dev check
```

**Step 2: 确认所有文件已提交**

```bash
git status
```

**Step 3: 最终提交（如有遗漏）**

```bash
git add -A
git commit -m "chore: 完成 Docker 部署配置"
```

---

## 完成后验证

部署完成后，执行以下命令验证：

```bash
# 1. 构建镜像
cd deploy/docker
docker compose build

# 2. 启动服务（使用环境变量）
TUSHARE_TOKEN=your_token docker compose up -d

# 3. 检查服务状态
docker compose ps

# 4. 健康检查
curl http://localhost:8000/healthz
curl http://localhost:4200/api/health

# 5. 查看日志
docker compose logs -f
```

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `.dockerignore` | 创建 | 排除不必要文件 |
| `deploy/docker/Dockerfile` | 创建 | 镜像构建配置 |
| `deploy/docker/docker-compose.yml` | 创建 | 容器编排配置 |
| `deploy/docker/.env.example` | 创建 | 环境变量模板 |
| `deploy/docker/README.md` | 创建 | 部署说明 |
| `apps/port/src/ditto_port/registry/infra/config.py` | 修改 | 支持 LOG_DIR |
| `packages/datahub/src/ditto_datahub/config/data_store.py` | 修改 | 支持 logs_path 覆盖 |
| `deploy/observability/docker-compose.yml` | 修改 | Vector 日志挂载 |
| `deploy/observability/vector.toml` | 修改 | 分离日志源 |
| `.gitignore` | 修改 | 忽略 .env.local |
