# Ditto 部署拓扑文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-08**

---

## 1. 部署目标与约束

### 1.1 核心目标

1. **单机闭环**：Windows 10/11 本地完整运行，不依赖云服务
2. **简单可靠**：最小化运维负担，故障恢复简单
3. **可证明存活**：心跳机制证明系统正常运行
4. **并发安全**：明确写锁策略，避免数据竞争

### 1.2 关键约束

- **硬件**：普通 PC（8GB+ RAM，100GB+ SSD）
- **网络**：仅需外网访问数据源，无需内网服务
- **运维**：个人开发者，无专职运维
- **监控**：外部心跳（Telagram/钉钉），不依赖本机监控

---

## 2. 整体部署架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Windows 10/11 本地主机                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Pixi 环境管理                                │   │
│  │  Python 3.11+ / Node.js 20+ / 所有依赖                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌───────────────────────┐    ┌───────────────────────┐                │
│  │    DittoServer        │    │    DittoWeb           │                │
│  │    (FastAPI)          │    │    (Next.js)          │                │
│  │    Port: 8000         │    │    Port: 3000         │                │
│  │                       │    │                       │                │
│  │  + APScheduler        │    │  + Dev Server         │                │
│  │  + HeartbeatService   │    │    (or Static Build)  │                │
│  └───────────┬───────────┘    └───────────┬───────────┘                │
│              │                            │                             │
│              │ HTTP/WS                    │ HTTP                        │
│              ▼                            ▼                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      数据存储层                                  │   │
│  │                                                                  │   │
│  │  ┌─────────────────────┐    ┌─────────────────────┐             │   │
│  │  │  DuckDB             │    │  SQLite             │             │   │
│  │  │  data/warehouse.db  │    │  ledger/trading.db  │             │   │
│  │  │                     │    │  (WAL Mode)         │             │   │
│  │  │  - K线/因子/Regime  │    │  - 调仓计划/持仓    │             │   │
│  │  │  - 回测结果         │    │  - 风控事件/状态    │             │   │
│  │  └─────────────────────┘    └─────────────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      外部通信                                    │   │
│  │                                                                  │   │
│  │  → Tushare Pro API (数据采集)                                   │   │
│  │  → AkShare API (数据校验)                                       │   │
│  │  → Telagram/钉钉 Webhook (心跳通知)                                 │   │
│  │  → 邮件 SMTP (备用通知)                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
D:\Ditto\                              # 项目根目录
├── apps/
│   ├── server/                        # FastAPI 后端
│   │   ├── src/
│   │   │   ├── api/                   # HTTP 接口
│   │   │   ├── services/              # 应用服务
│   │   │   ├── scheduler/             # APScheduler 作业
│   │   │   └── main.py
│   │   └── pyproject.toml
│   │
│   └── web/                           # Next.js 前端
│       ├── src/
│       │   ├── app/
│       │   ├── components/
│       │   └── stores/
│       └── package.json
│
├── packages/
│   └── core/                          # 核心库
│       └── ditto/
│           ├── data/
│           ├── engine/
│           ├── strategy/
│           ├── portfolio/
│           └── config/
│
├── data/                              # 数据目录
│   ├── warehouse.duckdb              # DuckDB 主库
│   ├── golden/                       # Golden Dataset
│   └── raw/                          # 原始数据（可选）
│
├── ledger/                            # 账本目录
│   └── trading.db                    # SQLite 账本库
│
├── backups/                           # 备份目录
│   ├── warehouse_YYYYMMDD.duckdb
│   └── trading_YYYYMMDD.db
│
├── logs/                              # 日志目录
│   ├── ditto_YYYYMMDD.log
│   └── archived/
│
├── config/                            # 配置目录
│   ├── settings.toml                 # 主配置
│   ├── secrets.toml                  # 敏感配置（Git 忽略）
│   └── strategies/                   # 策略配置
│       └── etf_rotation.toml
│
├── research/                          # 研究目录
│   ├── notebooks/
│   ├── experiments/
│   └── reports/
│
├── scripts/                           # 运维脚本
│   ├── start_all.ps1                 # 一键启动
│   ├── stop_all.ps1                  # 一键停止
│   ├── backup.ps1                    # 备份脚本
│   └── health_check.ps1              # 健康检查
│
├── docs/                              # 文档目录
│
├── pixi.toml                          # Pixi 项目配置
└── .gitignore
```

---

## 4. 环境配置管理（Pixi）

### 4.1 pixi.toml 配置

```toml
[project]
name = "ditto"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["win-64"]

[dependencies]
python = ">=3.11"
polars = ">=0.20"
duckdb = ">=0.9"
fastapi = ">=0.100"
uvicorn = ">=0.23"
pydantic = ">=2.0"
pydantic-settings = ">=2.0"
loguru = ">=0.7"
httpx = ">=0.25"
apscheduler = ">=3.10"
tushare = ">=1.2"
akshare = ">=1.10"

[tasks]
server = "cd apps/server && uvicorn src.main:app --reload --port 8000"
web = "cd apps/web && npm run dev"
test = "pytest packages/core/tests -v"
backup = "powershell -File scripts/backup.ps1"
```

### 4.2 Secrets 与敏感信息管理

本小节定义 Ditto 在部署与运行时对 **秘钥（Secrets）与敏感信息** 的管理规范，目标是：

- 避免 API Token / 交易账号 等敏感信息泄露；
- 避免敏感信息出现在代码仓库、日志或对话中；
- 一旦疑似泄露，有明确的应急步骤。

---

#### 4.2.1 敏感信息范围

默认视为“敏感”的包括但不限于：

- 第三方数据源 Token：
  - 如：Tushare Token、AkShare 私有 Token（若有）；
- 券商/交易接口相关信息：
  - 账号、密码、交易接口 Token、证书文件路径等；
- 本地服务访问凭证（若未来扩展）：
  - 数据库密码；
  - 内网服务访问 Token 等。

---

#### 4.2.2 存储规范

1. **禁止写死在代码中**
   - Python/TypeScript 等代码中禁止出现类似：
     - `"YOUR_TUSHARE_TOKEN_HERE"`
     - `"broker_password = 'xxx'"` 等字面量。
   - 统一通过 **环境变量 + Settings** 获取，例如：
     - `DTT_TUSHARE_TOKEN`
     - `DTT_BROKER_API_KEY`

2. **优先使用本地环境文件 / 凭据管理器**
   - 推荐方式：
     - 在本机使用 `.env.local` / `.env.development.local`（**不要提交到 Git**）；
     - 或使用 Windows 凭据管理器保存长期 Token，由 Settings 读取。
   - `.env*` 文件必须在 `.gitignore` 中明确忽略。

3. **Secrets 与配置分离**
   - `settings.toml` / `config.yaml` 等配置文件中只保存：
     - 非敏感配置（路径、开关、数值参数）；
   - 涉及 Token / 密码的字段统一留空或使用占位符，并通过环境变量补全。

---

#### 4.2.3 日志与备份中的安全要求

1. **日志**
   - 日志内容禁止输出：
     - 完整 Token/密码；
     - 完整账号信息；
   - 若必须记录（用于调试），应只保留：
     - 前后若干字符（例如前 4 位 + 后 4 位，中间用 `***` 替代）。

2. **备份**
   - DuckDB / SQLite 等备份文件可能包含交易记录、风险事件等敏感信息：
     - 备份存放路径应避免同步到公开云盘；
     - 若同步到云盘，需使用加密盘或受限权限的目录。

---

#### 4.2.4 仓库安全与泄露应急

1. **Git 仓库规范**
   - `.gitignore` 中应至少包含：
     - `.env*`
     - `secrets/`
     - `*.db` / `*.sqlite`（包含真实数据的文件）
   - 禁止将真实生产数据库、API Token 文件提交到仓库。

2. **疑似泄露的应急步骤**

一旦发现（或怀疑）以下情况：

- 将 `.env` / Token 文件误提交到远端仓库；
- 在公开对话或截图中暴露了完整 Token；

必须执行：

1. 立即在相应服务（Tushare、券商等）**废弃该 Token / 修改密码**；
2. 生成新的 Token，并更新本地 `.env` / 凭据；
3. 在 `risk_events` 中记录一次类型为 `SECURITY_ALERT` 的事件（方便追踪）；
4. 评估是否需要在《风险宪法》中补充相应的安全条款或经验总结。

---

本小节与：

- `05_observability.md` 中关于日志内容的要求；

共同构成 Ditto 的基础安全规范。


---

## 5. 任务调度（APScheduler）

**核心设计**：使用 APScheduler 内嵌在 DittoServer 进程中，避免 Windows 任务计划程序的脆弱性。

### 5.1 调度任务清单

| 任务 | 触发时间 | 职责 |
|------|----------|------|
| daily_data_update | 交易日 17:00 | 数据采集 + 因子计算 + Regime 更新 |
| heartbeat | 每小时整点 | 发送心跳到Telagram/钉钉 |
| data_validation | 交易日 18:00 | 双源数据校验 |
| daily_backup | 每天 22:00 | DuckDB + SQLite 备份 |
| factor_health_check | 每周一 9:00 | 因子健康度检查 |

### 5.2 调度器实现要点

```python
scheduler = AsyncIOScheduler(
    timezone="Asia/Shanghai",
    job_defaults={
        'coalesce': True,           # 合并错过的任务
        'max_instances': 1,          # 最多同时运行 1 个实例
        'misfire_grace_time': 3600,  # 错过后 1 小时内仍可执行
    }
)
```

---

## 6. 心跳机制

### 6.1 设计原则

> **"死人不会说话"** —— 监控系统本身挂了无法报警

因此心跳必须发送到**外部系统**（Telagram/钉钉/邮件），而非本机监控。

### 6.2 心跳内容

```
🤖 Ditto Heartbeat
Time: 2024-12-08 15:00
Status: ✅ OK | Data: 2024-12-06
Kill Switch: Inactive
```

### 6.3 异常时发送详情

```
🤖 Ditto Heartbeat
Time: 2024-12-08 15:00
Status: ❌ ERROR | Kill Switch Level 2 Active
Kill Switch: ACTIVE Level 2 - Drawdown 18.5%
Last Error: None
Action Required: Review and manually confirm
```

---

## 7. 数据库并发控制

### 7.1 核心原则

**"任何时刻只有一个写 DuckDB/SQLite 的进程"**

### 7.2 实现方式

- 使用文件锁 (`msvcrt.locking` on Windows)
- 写操作前获取锁，完成后释放
- 锁超时则抛出异常，不等待

### 7.3 SQLite WAL 模式

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
```

---

## 8. 备份策略

### 8.1 备份内容

| 数据 | 频率 | 保留期 |
|------|------|--------|
| DuckDB (warehouse) | 每日 | 30 天 |
| SQLite (trading) | 每日 | 30 天 |
| 配置文件 | 每日 | 30 天 |
| 日志文件 | 每周 | 90 天 |

### 8.2 备份恢复流程

1. 停止所有服务
2. 备份当前损坏数据（以防万一）
3. 从备份恢复
4. 重启服务
5. 验证健康检查

---

## 9. 健康检查

### 9.1 检查项

| 组件 | 检查内容 | 健康标准 |
|------|----------|----------|
| duckdb | 连接 + 查询 | 可查询 |
| sqlite | 连接 + 查询 | 可查询 |
| data_freshness | 最新数据日期 | ≤ 1 天 |
| scheduler | 运行状态 | 正在运行 |
| kill_switch | 触发状态 | 未触发 |

### 9.2 API 端点

- `GET /healthz` - 简单存活检查
- `GET /health` - 详细健康报告

---

## 10. Runbook（故障处理手册）

### 10.1 收不到心跳

```
1. 检查网络连接
2. 远程登录主机
3. 检查 DittoServer 进程：Get-Process python | Where CommandLine -like "*uvicorn*"
4. 查看最近日志：Get-Content logs\ditto_*.log -Tail 100
5. 如果进程不存在，重启：.\scripts\start_all.ps1
6. 如果持续失败，检查磁盘空间和内存
```

### 10.2 数据更新失败

```
1. 检查 Tushare 积分和 API 状态
2. 检查网络是否能访问 api.tushare.pro
3. 查看日志中的具体错误
4. 如果 Tushare 不可用，手动触发 AkShare 降级：
   python -m ditto.tasks.daily_update --source akshare
5. 如果都不可用，记录风控事件，暂停自动交易
```

### 10.3 Kill Switch 触发

```
1. 确认回撤数值正确（检查持仓市值计算）
2. 分析回撤原因（市场系统性下跌 vs 策略问题）
3. 检查 Regime 是否正确识别
4. 如果是市场系统性下跌且策略正常：
   - 等待市场稳定
   - 人工评估后解除 Kill Switch
5. 如果是策略问题：
   - 保持 Kill Switch 激活
   - 分析策略失效原因
   - 修复后重新回测验证
```

### 10.4 数据库损坏

```
1. 停止所有服务：.\scripts\stop_all.ps1
2. 备份损坏文件：Move-Item data\warehouse.duckdb data\warehouse.duckdb.corrupted
3. 恢复最近备份：Copy-Item backups\warehouse_latest.duckdb data\warehouse.duckdb
4. 重启服务：.\scripts\start_all.ps1
5. 验证：Invoke-WebRequest http://localhost:8000/health
6. 如果备份也损坏，需要重新采集历史数据
```

---

*本部署拓扑文档定义了 Ditto Phase 0–1 的完整部署架构。*
