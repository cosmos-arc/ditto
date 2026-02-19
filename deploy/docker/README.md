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
