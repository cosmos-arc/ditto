# Ditto 项目运维手册

**版本：v2.0**

**最后更新：2026-03-04**

---

## 目录

1. [第一部分：开发者快速入门](#第一部分开发者快速入门)
   - [1.1 环境准备](#11-环境准备)
   - [1.2 常用开发命令](#12-常用开发命令)
   - [1.3 测试与质量检查](#13-测试与质量检查)
   - [1.4 调试与日志查看](#14-调试与日志查看)
2. [第二部分：Docker 部署](#第二部分docker-部署)
3. [第三部分：运维深度指南](#第三部分运维深度指南)
   - [3.1 服务部署与启动](#31-服务部署与启动)
   - [3.2 配置管理](#32-配置管理)
   - [3.3 监控与告警](#33-监控与告警)
   - [3.4 日志管理](#34-日志管理)
   - [3.5 数据备份与恢复](#35-数据备份与恢复)
   - [3.6 定时任务管理](#36-定时任务管理)
   - [3.7 故障排查 Runbook](#37-故障排查-runbook)
4. [第四部分：E2E 验证系统](#第四部分e2e-验证系统)
5. [附录](#附录)

---

## 第一部分：开发者快速入门

### 1.1 环境准备

#### 1.1.1 系统要求

| 组件 | 最低要求 | 推荐配置 |
|------|----------|----------|
| 操作系统 | Windows 10/11, Linux | Windows 11 / Ubuntu 22.04 |
| Python | 3.13+ | 3.13.x |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 10GB | 50GB+ SSD |

#### 1.1.2 安装 Pixi

Pixi 是项目的包管理器和任务运行器。

```bash
# Linux/macOS
curl -fsSL https://pixi.sh/install.sh | bash

# Windows (PowerShell)
iwr -useb https://pixi.sh/install.ps1 | iex
```

#### 1.1.3 初始化项目

```bash
# 克隆项目
git clone <repo-url> ditto
cd ditto

# 安装依赖（开发环境）
pixi install

# 安装 pre-commit hooks
pixi run -e dev pre-commit-install
```

#### 1.1.4 配置 API Token

Tushare API Token 和 FRED API Key 通过系统密钥管理（keyring），不写入配置文件：

```bash
# 设置 Tushare Token（首次配置）
pixi run -e dev python -c "
import keyring
keyring.set_password('tushare', 'token', 'YOUR_TOKEN_HERE')
"

# 设置 FRED API Key（美国宏观数据）
pixi run -e dev python -c "
import keyring
keyring.set_password('fred', 'api_key', 'YOUR_API_KEY_HERE')
"

# 验证 Token
pixi run -e dev python -c "
import keyring
token = keyring.get_password('tushare', 'token')
api_key = keyring.get_password('fred', 'api_key')
print(f'Tushare: {\"已配置\" if token else \"未配置\"}')
print(f'FRED: {\"已配置\" if api_key else \"未配置\"}')
"
```

---

### 1.2 常用开发命令

#### 1.2.1 服务启动

| 命令 | 说明 |
|------|------|
| `pixi run dev` | 开发模式启动（热重载，端口 8000） |
| `pixi run server` | 生产模式启动（4 workers，端口 8000） |

#### 1.2.2 代码质量

| 命令 | 说明 |
|------|------|
| `pixi run -e dev check` | 快速验证（lint + fmt + type + test --fast） |
| `pixi run -e dev ci` | CI 完整检查 |
| `pixi run -e dev lint` | Ruff 代码检查 |
| `pixi run -e dev lint --fix` | 自动修复 lint 问题 |
| `pixi run -e dev fmt` | 代码格式化 |
| `pixi run -e dev type` | 类型检查（源码，strict） |
| `pixi run -e dev type --all` | 完整类型检查（含测试） |
| `pixi run -e dev arch-check` | 架构边界检查（Import Linter） |

#### 1.2.3 其他命令

| 命令 | 说明 |
|------|------|
| `pixi run clean` | 清理缓存（pytest/ruff/__pycache__） |
| `pixi run -e dev pre-commit-run` | 运行 pre-commit hooks |
| `pixi run -e dev pre-commit-update` | 更新 pre-commit hooks 版本 |

---

### 1.3 测试与质量检查

#### 1.3.1 测试命令

```bash
# 默认：单元测试（并行）
pixi run -e dev test

# 只运行单元测试
pixi run -e dev test --unit

# 只运行集成测试（串行）
pixi run -e dev test --integration

# 快速测试（跳过 slow/integration）
pixi run -e dev test --fast

# 带覆盖率报告
pixi run -e dev test --cov

# 覆盖率 XML（CI 用）
pixi run -e dev test --cov-xml

# 支持 inline-snapshot
pixi run -e dev test --snapshot

# E2E 验证测试
pixi run -e dev pytest tests/e2e/ -v
```

#### 1.3.2 测试覆盖率要求

- **分支覆盖率**：≥ 80%
- **新功能**：必须有单元测试
- **API 变更**：必须有集成测试

#### 1.3.3 质量门禁

提交前必须通过：

```bash
pixi run -e dev check
```

包含：
- [ ] basedpyright 类型检查通过
- [ ] ruff 检查通过
- [ ] 测试通过
- [ ] 架构边界检查通过

---

### 1.4 调试与日志查看

#### 1.4.1 日志位置

| 环境 | 日志路径 | 格式 |
|------|----------|------|
| 开发 | `data/logs/ditto.jsonl` | console |
| 生产 | `data/logs/ditto.jsonl` | json |

#### 1.4.2 查看日志

```bash
# 实时查看日志
tail -f data/logs/ditto.jsonl

# 查看最近 100 行
tail -n 100 data/logs/ditto.jsonl

# 过滤 ERROR 级别
cat data/logs/ditto.jsonl | jq 'select(.level == "ERROR")'
```

#### 1.4.3 日志级别

开发环境默认 `DEBUG`，可通过 `config/development/observability.env` 调整：

```bash
LOG_LEVEL=DEBUG  # DEBUG | INFO | WARNING | ERROR
```

---

## 第二部分：Docker 部署

### 2.1 架构概览

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

### 2.2 快速开始

#### 2.2.1 创建数据目录

```bash
sudo mkdir -p /opt/ditto/{data,prefect,logs/api,logs/job}
```

#### 2.2.2 配置环境变量

```bash
cd deploy/docker
cp .env.example .env.local
# 编辑 .env.local，设置 TUSHARE_TOKEN
```

#### 2.2.3 构建并启动

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose --env-file .env.local up -d
```

#### 2.2.4 验证服务

```bash
# 健康检查
curl http://localhost:8000/healthz
curl http://localhost:4200/api/health

# 查看日志
docker compose logs -f ditto-api
docker compose logs -f ditto-job
```

### 2.3 访问地址

| 服务 | 地址 |
|------|------|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Prefect UI | http://localhost:4200 |

### 2.4 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DITTO_VERSION | 镜像版本 | latest |
| ENVIRONMENT | 运行环境 | production |
| DITTO_DATA_PATH | 数据目录 | /opt/ditto/data |
| DITTO_LOGS_PATH | 日志目录 | /opt/ditto/logs |
| PREFECT_DATA_PATH | Prefect 数据目录 | /opt/ditto/prefect |
| TUSHARE_TOKEN | Tushare API Token | (必须设置) |

### 2.5 资源配置

| 服务 | 内存限制 | 说明 |
|------|----------|------|
| ditto-api | 1GB | API 服务 |
| ditto-job | 2GB | Prefect Server + Worker |

### 2.6 日常运维

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

### 2.7 故障排查

#### 容器无法启动

```bash
# 查看容器日志
docker compose logs ditto-api
docker compose logs ditto-job

# 检查容器状态
docker compose ps
```

#### 权限问题

```bash
# 确保 Docker 用户有权限访问 /opt/ditto
sudo chown -R $USER:$USER /opt/ditto
```

---

## 第三部分：运维深度指南

### 3.1 服务部署与启动

#### 3.1.1 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        服务拓扑                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────┐    ┌───────────────────────┐         │
│  │    DittoServer        │    │    Prefect Server     │         │
│  │    (FastAPI)          │    │                       │         │
│  │    Port: 8000         │    │    Port: 4200 (UI)    │         │
│  │                       │    │    SQLite 持久化      │         │
│  │  + Prefect Worker     │    │                       │         │
│  └───────────────────────┘    └───────────────────────┘         │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      数据存储层                            │  │
│  │  ┌─────────────────────┐    ┌─────────────────────┐       │  │
│  │  │  Parquet + DuckDB   │    │  SQLite             │       │  │
│  │  │  data/              │    │  data/metadata.db   │       │  │
│  │  └─────────────────────┘    └─────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.1.2 本地启动顺序（非 Docker）

```bash
# 1. 启动 Prefect Server（后台）
prefect server start --host 127.0.0.1 &

# 2. 等待 Server 就绪（约 5 秒）
sleep 5

# 3. 启动 Prefect Worker
prefect worker start --pool default-agent-pool &

# 4. 启动 FastAPI Server
pixi run server
```

#### 3.1.3 端口配置

| 服务 | 端口 | 说明 |
|------|------|------|
| FastAPI Server | 8000 | 主 API 服务 |
| Prefect Server UI | 4200 | 任务调度管理 |
| VictoriaMetrics | 8428 | Metrics 存储 |
| VictoriaLogs | 9428 | Logs 存储 |
| Grafana | 3000 | 可视化仪表盘 |
| Vector | 8686 | 日志采集 |

#### 3.1.4 资源需求

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| FastAPI Server | 1 核 | 512MB | - |
| Prefect Server | 1 核 | 256MB | 100MB |
| Prefect Worker | 1 核 | 512MB | - |
| SQLite | - | 256MB | 1GB |
| Parquet 数据 | - | - | 10GB+ |
| **总计** | 2-4 核 | 2GB | 15GB+ |

---

### 3.2 配置管理

#### 3.2.1 双层环境架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   环境控制层次（从外到内）                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: Pixi 环境 (依赖管理层)                                 │
│  ├── default → 生产依赖                                          │
│  └── dev      → default + 开发工具                               │
│                                                                  │
│  Layer 2: 运行时环境 (行为控制层)                                 │
│  └── ENVIRONMENT = development | testing | production           │
│                                                                  │
│  Layer 3: 可观测性开关 (细粒度控制层)                             │
│  └── 独立功能开关（OTEL 风格）                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.2.2 配置文件结构

```
config/
├── development/           # 开发环境
│   ├── system.env         # 系统配置
│   ├── observability.env  # 可观测性配置
│   ├── data_store.env     # 数据存储配置
│   ├── data_source.env    # 数据源配置
│   ├── dq.env             # 数据质量配置
│   └── notification.env   # 通知配置
├── testing/               # 测试环境
└── production/            # 生产环境
```

#### 3.2.3 核心配置项

**系统配置** (`system.env`):

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ENVIRONMENT` | 运行环境 | `development` |
| `TIMEZONE` | 时区 | `Asia/Shanghai` |
| `DEBUG` | 调试模式 | `false` |

**数据存储** (`data_store.env`):

| 配置项 | 说明 | 开发环境 | 生产环境 |
|--------|------|----------|----------|
| `DATA_ROOT` | 数据根目录 | `data` | `/data/ditto` |

**可观测性** (`observability.env`):

| 配置项 | 说明 | 开发环境 | 生产环境 |
|--------|------|----------|----------|
| `LOG_LEVEL` | 日志级别 | `DEBUG` | `INFO` |
| `LOG_FORMAT` | 日志格式 | `console` | `json` |
| `TRACING_ENABLED` | 链路追踪 | `true` | `true` |
| `TRACING_SAMPLE_RATE` | 采样率 | `1.0` | `0.1` |
| `METRICS_ENABLED` | 指标收集 | `true` | `true` |

**数据源** (`data_source.env`):

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `HTTP_BASE_URL` | Tushare API 地址 | `http://api.tushare.pro` |
| `HTTP_TIMEOUT` | 请求超时（秒） | `30.0` |
| `RETRY_MAX_ATTEMPTS` | 重试次数 | `3` |
| `RATE_LIMIT_PROFILE` | Tushare 运行时限流预设：`free`、`paid`（兼容别名 `premium`）或 `conservative`；非法值会在客户端初始化时 fail closed | `paid` |

**数据质量** (`dq.env`):

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `L1_ENABLED` | L1 格式校验 | `true` |
| `L2_ENABLED` | L2 业务规则 | `true` |
| `L3_ENABLED` | L3 统计异常 | `true` |
| `QUARANTINE_ENABLED` | 隔离机制 | `true` |

#### 3.2.4 环境切换

| 场景 | Pixi 环境 | ENVIRONMENT | 命令示例 |
|------|-----------|-------------|----------|
| 本地开发 | `dev` | `development` | `pixi run -e dev pytest` |
| 测试执行 | `dev` | `testing` | `pixi run -e dev pytest` |
| 生产部署 | `default` | `production` | `pixi run server` |

---

### 3.3 监控与告警

#### 3.3.1 可观测性栈

| 服务 | 版本 | 端口 | 内存限制 | 保留期 |
|------|------|------|----------|--------|
| VictoriaMetrics | v1.104.0 | 8428 | 256M | 90 天 |
| VictoriaLogs | v1.37.0 | 9428 | 256M | 30 天 |
| Vector | v0.52.0 | 8686 | 128M | - |
| Grafana | 11.1.0 | 3000 | 256M | - |

**总资源占用**：~400MB RAM，~2.6GB 磁盘（30 天）

#### 3.3.2 启动监控栈

```bash
# 启动
cd deploy/observability
docker-compose up -d

# 停止
docker-compose down

# 查看状态
docker-compose ps
```

#### 3.3.3 预定义指标

| 指标名称 | 说明 |
|----------|------|
| `ditto.data.update.duration` | 数据更新耗时 |
| `ditto.data.records_total` | 数据记录总数 |
| `ditto.data.freshness_days` | 数据新鲜度（天） |
| `ditto.factor.calc.duration` | 因子计算耗时 |
| `ditto.factor.ic` | 因子 IC 值 |
| `ditto.signal.total` | 信号总数 |
| `ditto.rebalance.total` | 调仓次数 |
| `ditto.risk.kill_switch_level` | 熔断级别 |
| `ditto.cache.hit_rate` | 缓存命中率 |
| `ditto.sql.query.duration` | SQL 查询耗时 |
| `ditto.sql.slow_query_total` | 慢查询计数 |

#### 3.3.4 健康检查端点

| 端点 | 说明 |
|------|------|
| `/healthz` | 简单存活检查 |
| `/health` | 详细健康报告 |
| `/api/v1/status` | 系统状态信息 |

**健康检查内容**：

| 组件 | 检查内容 | 健康标准 |
|------|----------|----------|
| sqlite | 连接 + 查询 | 可查询 |
| parquet | 文件可读 | 可读取 |
| data_freshness | 最新数据日期 | ≤ 1 天 |
| prefect_server | API 响应 | 可访问 |
| prefect_worker | 运行状态 | 正在运行 |
| kill_switch | 触发状态 | 未触发 |

#### 3.3.5 心跳机制

心跳发送到外部系统（Telegram/钉钉），不依赖本机监控。

**心跳内容示例**：
```
🤖 Ditto Heartbeat
Time: 2026-03-04 15:00
Status: ✅ OK | Data: 2026-03-03
Kill Switch: Inactive
Prefect: 3 flows healthy
```

**异常心跳示例**：
```
🤖 Ditto Heartbeat
Time: 2026-03-04 15:00
Status: ❌ ERROR
Kill Switch: ACTIVE Level 2 - Drawdown 18.5%
Last Flow Run: daily-ingest FAILED
Action Required: Review and manually confirm
```

---

### 3.4 日志管理

#### 3.4.1 日志流向

```
App (Loguru) → data/logs/ditto.jsonl → Vector → VictoriaLogs
                                            ↓
                                        Grafana
```

#### 3.4.2 日志级别预设

| 环境 | 级别 | 格式 | 文件输出 |
|------|------|------|----------|
| Development | DEBUG | console | yes |
| Testing | WARNING | console | no |
| Production | INFO | json | yes |

#### 3.4.3 日志查询

**命令行**：
```bash
# 查看最近日志
tail -f data/logs/ditto.jsonl

# 过滤 JSON 日志
cat data/logs/ditto.jsonl | jq 'select(.level == "ERROR")'
```

**VictoriaLogs 查询**：
```bash
# 查询最近错误
curl -G 'http://localhost:9428/select/logsql/query' \
  --data-urlencode 'query=level:ERROR' \
  --data-urlencode 'limit=100'
```

**Grafana Dashboard**：
- 访问 `http://localhost:3000`
- 使用 Explore 页面查询日志

---

### 3.5 数据备份与恢复

#### 3.5.1 备份策略

| 数据 | 频率 | 保留期 |
|------|------|--------|
| Parquet 数据 | 每日 | 30 天 |
| SQLite 元数据 | 每日 | 30 天 |
| 配置文件 | 每日 | 30 天 |
| Prefect 数据库 | 每周 | 30 天 |
| 日志文件 | 每周 | 90 天 |

#### 3.5.2 备份脚本（Linux）

```bash
#!/bin/bash
# scripts/backup.sh
DATE=$(date +%Y%m%d)
BACKUP_DIR="/opt/ditto/backups/$DATE"

mkdir -p "$BACKUP_DIR"

# 备份 Parquet 数据
cp -r /opt/ditto/data/market "$BACKUP_DIR/market"
cp -r /opt/ditto/data/metadata "$BACKUP_DIR/metadata"

# 备份 SQLite
cp /opt/ditto/data/metadata/metadata.sqlite "$BACKUP_DIR/"

# 备份配置
cp -r /opt/ditto/config "$BACKUP_DIR/config"

# 清理旧备份（保留 30 天）
find /opt/ditto/backups -type d -mtime +30 -exec rm -rf {} +

echo "Backup completed: $BACKUP_DIR"
```

#### 3.5.3 恢复步骤

```bash
# 1. 停止所有服务
docker compose down  # 或本地停止

# 2. 恢复数据
cp -r backups/20260304/market /opt/ditto/data/
cp -r backups/20260304/metadata /opt/ditto/data/
cp backups/20260304/metadata.sqlite /opt/ditto/data/metadata/

# 3. 重启服务
docker compose up -d  # 或本地启动

# 4. 验证数据完整性
curl http://localhost:8000/health
```

---

### 3.6 定时任务管理

#### 3.6.1 任务调度清单

| 任务 | 触发时间 | 职责 |
|------|----------|------|
| `daily_ingest_flow` | 交易日 17:00 | 日历 + 证券 + K 线 + 复权因子 |
| `dq_batch_check` | 交易日 18:00 | L3 统计异常检测 |
| `heartbeat_flow` | 每小时整点 | 发送心跳到 Telegram/钉钉 |
| `daily_backup` | 每天 22:00 | Parquet + SQLite 备份 |
| `factor_health_check` | 每周一 9:00 | 因子健康度检查 |

#### 3.6.2 Prefect 日常命令

```bash
# 查看所有 Deployments
prefect deployment ls

# 查看最近运行
prefect flow-run ls --limit 10

# 手动触发
prefect deployment run "daily-ingest/daily-ingest-scheduled"

# 手动触发（带参数）
prefect deployment run "daily-ingest/daily-ingest-scheduled" \
    --param trade_date="2026-03-03"

# 取消运行
prefect flow-run cancel <run-id>

# 查看日志
prefect flow-run logs <run-id>

# 补数据
prefect deployment run "backfill/backfill-scheduled" \
    --param start_date="2026-01-01" \
    --param end_date="2026-01-31"
```

#### 3.6.3 Prefect UI

访问 `http://localhost:4200`：
- 查看任务执行状态
- 手动触发任务
- 查看执行日志
- 管理调度配置

---

### 3.7 故障排查 Runbook

#### 3.7.1 收不到心跳

```
1. 检查网络连接
2. 远程登录主机
3. 检查 Prefect Worker 进程：
   ps aux | grep prefect
4. 查看 Prefect UI：http://localhost:4200
5. 查看最近日志：tail -n 100 data/logs/ditto.jsonl
6. 如果 Worker 不存在，重启服务
```

#### 3.7.2 数据摄取失败

```
1. 查看 Prefect UI 中的 Flow Run 详情
2. 检查具体 Task 的错误信息
3. 检查 Tushare 积分和 API 状态
4. 如果 Tushare 不可用，手动触发 AkShare 降级：
   prefect deployment run "daily-ingest/..." --param source="akshare"
5. 修复后手动重跑：
   prefect deployment run "daily-ingest/..." --param trade_date="2026-03-03"
```

#### 3.7.3 Prefect Server 无响应

```
1. 检查进程：ps aux | grep prefect
2. 检查端口：netstat -tlnp | grep 4200
3. 查看日志：tail -n 100 ~/.prefect/prefect.log
4. 重启 Prefect：
   pkill -f prefect
   # 然后重新启动服务
```

#### 3.7.4 补数据流程

```
1. 确定需要补的日期范围
2. 运行 backfill Flow：
   prefect deployment run "backfill/backfill-scheduled" \
       --param start_date="2026-01-01" \
       --param end_date="2026-01-31"
3. 在 Prefect UI 监控进度
4. 完成后验证数据完整性
```

#### 3.7.5 服务资源不足

```
1. 检查内存使用：free -h
2. 检查磁盘空间：df -h
3. 清理旧日志和备份：
   - 日志保留 90 天
   - 备份保留 30 天
4. 增加资源或迁移到更大机器
```

---

## 第四部分：E2E 验证系统

### 4.1 概述

E2E（端到端）验证系统用于确保数据摄入、存储、查询的全链路正确性。基于黄金数据集进行验收测试。

### 4.2 黄金数据集

黄金数据集包含 25 个精选标的，覆盖：
- 流动性分层（主板、创业板、科创板）
- 市场板块（沪市、深市、北交所）
- 资产类型（股票、ETF、指数）

**配置文件**：`config/default/golden_dataset.yml`

### 4.3 运行 E2E 测试

```bash
# 准备 E2E 测试数据
pixi run -e dev python tests/scripts/prepare_e2e_data.py

# 运行 E2E 测试
pixi run -e dev pytest tests/e2e/ -v

# 生成验收报告
# 报告自动保存至 tests/reports/e2e_validation_YYYYMMDD.md
```

### 4.4 E2E 测试模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 摄入测试 | `test_ingestion.py` | 数据摄入正确性 |
| 存储测试 | `test_storage.py` | 存储层读写正确性 |
| 查询测试 | `test_query.py` | 数据查询正确性 |
| 质量测试 | `test_quality.py` | 数据质量验证 |
| 管道测试 | `test_pipeline.py` | 全链路集成测试 |

### 4.5 验收报告

测试完成后自动生成 Markdown 格式的验收报告，包含：
- 各阶段测试结果
- 数据完整性统计
- 质量检查摘要
- 问题列表（如有）

**报告路径**：`tests/reports/e2e_validation_YYYYMMDD.md`

---

## 附录

### A. 关键文件路径

| 功能 | 路径 |
|------|------|
| 服务器主入口 | `packages/apps/src/ditto_apps/main.py` |
| CLI 入口 | `packages/apps/src/ditto_apps/cli/main.py` |
| Pixi 配置 | `pixi.toml` |
| 生产配置 | `config/production/` |
| 开发配置 | `config/development/` |
| 可观测性模块 | `packages/platform/src/ditto_platform/foundation/observability/` |
| Docker Compose | `deploy/docker/docker-compose.yml` |
| Dockerfile | `deploy/docker/Dockerfile` |
| 可观测性 Docker | `deploy/observability/docker-compose.yml` |
| Vector 配置 | `deploy/observability/vector.toml` |
| Grafana 数据源 | `deploy/observability/grafana/provisioning/datasources/` |
| Grafana Dashboard | `deploy/observability/grafana/provisioning/dashboards/` |
| E2E 测试 | `tests/e2e/` |

### B. 常用端口汇总

| 服务 | 端口 | 访问地址 |
|------|------|----------|
| FastAPI | 8000 | http://localhost:8000 |
| Prefect UI | 4200 | http://localhost:4200 |
| Grafana | 3000 | http://localhost:3000 |
| VictoriaMetrics | 8428 | http://localhost:8428 |
| VictoriaLogs | 9428 | http://localhost:9428 |

### C. 相关文档

- [配置系统手册](/docs/configuration.md)
- [数据集手册](/docs/data-manual.md)
- [Docker 部署文档](/deploy/docker/README.md)
- [可观测性部署文档](/deploy/observability/README.md)
