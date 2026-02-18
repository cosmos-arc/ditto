# Docker 部署设计

> 版本: v1.0.0
> 日期: 2026-02-18
> 状态: 设计完成

## 概述

本文档定义 Ditto 量化系统的 Docker 部署方案，支持本地开发/测试和单机生产环境。

### 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 容器架构 | 2 容器（api + job） | 职责分离，故障隔离 |
| Prefect 部署 | 自托管 + SQLite | 简化部署，单机够用 |
| 存储持久化 | Bind Mount | 方便备份和直接访问 |
| 配置管理 | 混合（环境变量 + 打包配置） | 敏感信息隔离 |
| 镜像构建 | Pixi 单阶段 | 依赖精确，构建简单 |
| 网络暴露 | 直接端口 | 单机部署，减少复杂度 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Host                                   │
│                      (/opt/ditto/)                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────────────┐  ┌───────────────────────────────┐  │
│  │      ditto-api            │  │      ditto-job                │  │
│  │      FastAPI :8000        │  │      Prefect Server + Worker  │  │
│  │                           │  │      :4200                    │  │
│  │  内置 config/             │  │  内置 config/                 │  │
│  └─────────────┬─────────────┘  └───────────────┬───────────────┘  │
│                │                                │                   │
│                └────────────────┬───────────────┘                   │
│                                 ▼                                    │
│                    ┌────────────────────────┐                       │
│                    │  ditto-network         │                       │
│                    └────────────────────────┘                       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  /opt/ditto/                                                 │   │
│  │  ├── data/             ← 业务数据 (parquet/sqlite/duckdb)   │   │
│  │  ├── prefect/          ← Prefect SQLite                     │   │
│  │  └── logs/             ← 日志                                │   │
│  │      ├── api/          ← API 日志                           │   │
│  │      └── job/          ← Job 日志                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  observability (独立 docker-compose)                         │   │
│  │  - VictoriaMetrics (:8428)  - Grafana (:3000)               │   │
│  │  - VictoriaLogs (:9428)     - Vector                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 容器配置

### ditto-api（FastAPI 服务）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|----------|----------|------|
| CPU | 0.5 | 1-2 | 量化计算较少，主要 I/O |
| 内存 | 512MB | 1GB | 预留 polars 操作空间 |
| 副本 | 1 | 1 | 单机无需多副本 |

### ditto-job（Prefect Server + Worker）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|----------|----------|------|
| CPU | 1 | 2-4 | 数据采集和转换计算密集 |
| 内存 | 1GB | 2GB | polars 处理大数据需要 |
| 存储 | 1GB | 5GB | Prefect SQLite + 临时文件 |
| 副本 | 1 | 1 | SQLite 不支持多写 |

### observability（独立部署）

| 服务 | 内存 | CPU | 存储 |
|------|------|-----|------|
| VictoriaMetrics | 256MB | 0.5 | 10GB（90天保留） |
| VictoriaLogs | 256MB | 0.5 | 5GB（30天保留） |
| Vector | 128MB | 0.25 | - |
| Grafana | 256MB | 0.25 | 1GB |

### 主机最低要求

| 场景 | CPU | 内存 | 存储 |
|------|-----|------|------|
| 开发/测试 | 2 核 | 4GB | 50GB |
| 生产（小规模） | 4 核 | 8GB | 200GB |
| 生产（中规模） | 8 核 | 16GB | 500GB+ |

---

## 端口规划

| 服务 | 容器端口 | 主机端口 | 用途 |
|------|----------|----------|------|
| ditto-api | 8000 | 8000 | REST API |
| ditto-job | 4200 | 4200 | Prefect UI |
| VictoriaMetrics | 8428 | 8428 | Metrics 查询 |
| VictoriaLogs | 9428 | 9428 | Logs 查询 |
| Grafana | 3000 | 3000 | 可视化仪表盘 |

---

## 敏感信息管理

### Token 配置方式

项目使用 `DataSourceSettings.tushare_token` 字段，支持环境变量 `TUSHARE_TOKEN` 注入。

**Docker 部署推荐方式**：

```bash
# 方式 1：宿主机环境变量
export TUSHARE_TOKEN=your_actual_token
docker compose up -d

# 方式 2：启动时传入
TUSHARE_TOKEN=your_actual_token docker compose up -d

# 方式 3：使用 .env.local 文件（不提交到 git）
echo "TUSHARE_TOKEN=your_actual_token" > .env.local
docker compose --env-file .env.local up -d
```

**注意事项**：
- 本地开发继续使用 keyring
- Docker 环境使用环境变量（keyring 在容器内不可用）
- `.env.local` 必须加入 `.gitignore`

---

## 日志管理

### 日志目录结构

```
/opt/ditto/logs/
├── api/
│   └── ditto-api.json    # API 服务日志
└── job/
    └── ditto-job.json    # Job 服务日志
```

### 日志配置

容器内通过 `LOG_DIR` 环境变量区分：

```yaml
# ditto-api
environment:
  - LOG_DIR=/app/logs/api

# ditto-job
environment:
  - LOG_DIR=/app/logs/job
```

### Vector 配置更新

```toml
# API 日志源
[sources.api_logs]
type = "file"
include = ["/logs/api/*.json"]
read_from = "beginning"

# Job 日志源
[sources.job_logs]
type = "file"
include = ["/logs/job/*.json"]
read_from = "beginning"

# 为日志添加来源标签
[transforms.api_logs_transform]
type = "remap"
inputs = ["api_logs"]
source = '''
. = parse_json!(.message)
.source = "ditto-api"
'''

[transforms.job_logs_transform]
type = "remap"
inputs = ["job_logs"]
source = '''
. = parse_json!(.message)
.source = "ditto-job"
'''

# 合并发送到 VictoriaLogs
[sinks.victorialogs]
type = "elasticsearch"
inputs = ["api_logs_transform", "job_logs_transform"]
endpoints = ["http://victorialogs:9428/insert/elasticsearch/"]
index = "ditto-logs-%Y-%m-%d"
```

---

## 文件结构

```
deploy/
├── docker/
│   ├── Dockerfile              # 应用镜像
│   ├── docker-compose.yml      # 主应用编排
│   ├── .env.example            # 环境变量模板
│   └── README.md               # 部署说明
└── observability/
    ├── docker-compose.yml      # 可观测性栈（已有）
    ├── vector.toml             # Vector 配置（更新）
    └── ...
```

---

## 部署命令

### 首次部署

```bash
# 1. 创建数据目录
sudo mkdir -p /opt/ditto/{data,prefect,logs/api,logs/job}

# 2. 创建环境变量文件
cd deploy/docker
cp .env.example .env.local
# 编辑 .env.local，填入 TUSHARE_TOKEN

# 3. 构建镜像
docker compose build

# 4. 启动服务
docker compose --env-file .env.local up -d

# 5. 启动可观测性栈（可选）
cd ../observability
docker compose up -d
```

### 日常运维

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

# 健康检查
curl http://localhost:8000/healthz
curl http://localhost:4200/api/health
```

### 访问地址

| 服务 | 地址 |
|------|------|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Prefect UI | http://localhost:4200 |
| Grafana | http://localhost:3000 |

---

## 未来扩展

### 水平扩展方案

如需水平扩展，存储层需要调整：

| 方案 | 适用场景 | 改动成本 |
|------|----------|----------|
| MinIO（S3 兼容） | Parquet 文件共享 | 中 |
| PostgreSQL | 替换 SQLite/DuckDB | 中-高 |
| NFS/CephFS | 共享文件系统 | 低（但性能一般） |

当前架构的 `data_root` 统一入口已为未来迁移预留扩展点。

---

## 附录

### 相关文档

- [Observability 部署](../../deploy/observability/README.md)
- [配置系统规范](../configuration.md)
- [运维手册](../ops-manual.md)
