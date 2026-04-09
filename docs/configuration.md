# Ditto 配置系统操作手册

**版本：v2.0**

**最后更新：2026-03-04**

---

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [环境配置详解](#环境配置详解)
4. [配置文件详解](#配置文件详解)
5. [常用操作指南](#常用操作指南)
6. [故障排查](#故障排查)
7. [附录](#附录)

---

## 概述

Ditto 配置系统采用**分层架构**设计，支持多环境配置、路径管理和依赖注入集成。

### 核心概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **Environment** | 运行时环境标识 | `development`, `testing`, `production` |
| **Config File** | 环境特定的配置文件 | `config/development/data_store.env` |
| **Settings** | 配置模型类 | `DataStoreSettings`, `SystemSettings` |
| **ConfigProvider** | DI 配置提供者 | 组装所有配置的单一入口 |

### 配置流程图

```
┌──────────────┐    ┌───────────────┐    ┌──────────────────┐
│ ENVIRONMENT  │───→│ ConfigLoader  │───→│ load_env_file()  │
│  环境变量     │    │  定位文件      │    │  加载 .env       │
└──────────────┘    └───────────────┘    └──────────────────┘
                                                │
                                                ▼
┌──────────────┐    ┌───────────────┐    ┌──────────────────┐
│  业务代码     │←───│  DI Container │←───│ ConfigProvider   │
│  通过注入获取  │    │  注入配置      │    │  组装配置        │
└──────────────┘    └───────────────┘    └──────────────────┘
```

### 配置模块位置

| 模块 | 包路径 | 说明 |
|------|--------|------|
| 环境管理 | `ditto_infra.foundation.config` | 环境检测、配置加载 |
| 系统配置 | `ditto_infra.foundation.config.settings` | SystemSettings, ObservabilitySettings |
| 存储配置 | `ditto_data.config.data_store` | DataStoreSettings |
| 数据源配置 | `ditto_data.config.data_source` | DataSourceSettings |
| 通知配置 | `ditto_infra.services.notification.config` | NotificationSettings |
| 质量配置 | `ditto_data.quality.config` | DQSettings |

---

## 快速开始

### 1. 设置环境

```bash
# 开发环境（默认）
export ENVIRONMENT=development

# 测试环境
export ENVIRONMENT=testing

# 生产环境
export ENVIRONMENT=production
```

### 2. 配置 API Token

Tushare API Token 和 FRED API Key 通过系统密钥管理（keyring），**不应写入配置文件**：

```bash
# 设置 Tushare Token
pixi run -e dev python -c "
import keyring
keyring.set_password('tushare', 'token', 'YOUR_TOKEN_HERE')
"

# 设置 FRED API Key（美国宏观数据）
pixi run -e dev python -c "
import keyring
keyring.set_password('fred', 'api_key', 'YOUR_API_KEY_HERE')
"

# 验证配置
pixi run -e dev python -c "
import keyring
token = keyring.get_password('tushare', 'token')
api_key = keyring.get_password('fred', 'api_key')
print(f'Tushare: {\"已配置\" if token else \"未配置\"}')
print(f'FRED: {\"已配置\" if api_key else \"未配置\"}')
"
```

**Token 加载优先级**：环境变量 > keyring > 配置文件

```bash
# 临时使用（环境变量方式）
TUSHARE_TOKEN=your_token pixi run -e dev test
```

### 3. 查看当前配置

```bash
# 查看环境
pixi run -e dev python -c "
from ditto_infra.foundation.config import get_environment
print(f'当前环境: {get_environment().value}')
"

# 查看数据目录
pixi run -e dev python -c "
from dishka import make_container
from ditto_interfaces.registry.infra.config import ConfigProvider
from ditto_data.config.data_store import DataStoreSettings
import os
os.environ['ENVIRONMENT'] = 'development'
container = make_container(ConfigProvider())
settings = container.get(DataStoreSettings)
print(f'数据目录: {settings.data_root}')
print(f'SQLite: {settings.resolved_sqlite_path}')
container.close()
"
```

### 4. 修改配置

编辑对应的配置文件：

```bash
# 修改开发环境数据存储配置
vim config/development/data_store.env
```

---

## 环境配置详解

### 配置文件目录结构

```
config/
├── default/                    # 环境无关配置
│   └── dq_rules/              # 数据质量规则
│       ├── stock_daily.yml    # 股票日线规则
│       ├── etf_daily.yml      # ETF 日线规则
│       └── ...
│
├── development/               # 开发环境
│   ├── system.env            # 系统配置
│   ├── data_store.env        # 数据存储配置
│   ├── data_source.env       # 数据源配置
│   ├── observability.env     # 可观测性配置
│   ├── dq.env                # 数据质量配置
│   └── notification.env      # 通知配置
│
├── testing/                   # 测试环境（结构同上）
│
└── production/                # 生产环境（结构同上）
```

### 各环境配置差异

| 配置项 | development | testing | production |
|--------|-------------|---------|------------|
| `DATA_ROOT` | `data` | `.tmp/ditto` | `/data/ditto` |
| `DEBUG` | `true` | `true` | `false` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` |
| `LOG_FORMAT` | `console` | `console` | `json` |
| `RATE_LIMIT_PROFILE` | `free` | `free` | `paid` |

### 配置文件格式

配置文件使用 `.env` 格式，支持：

```bash
# 简单值
DATA_ROOT=data

# 布尔值
DEBUG=true

# 嵌套配置（使用双下划线）
SQL_ENGINE__ENABLE_PLAN_CACHE=true
SQL_ENGINE__PLAN_CACHE_SIZE=1000

# 注释
# SQLITE_PATH=data/metadata/metadata.sqlite
```

---

## 配置文件详解

### 1. system.env - 系统配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `ENVIRONMENT` | str | `development` | 运行环境（会被环境变量覆盖） |
| `TIMEZONE` | str | `Asia/Shanghai` | 系统时区 |
| `DEBUG` | bool | `false` | 调试模式 |

### 2. data_store.env - 数据存储配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `DATA_ROOT` | path | `data` | 数据根目录（所有路径从此派生） |
| `SQLITE_PATH` | path | 自动计算 | SQLite 路径覆盖 |
| `DUCKDB_PATH` | path | 自动计算 | DuckDB 路径覆盖 |
| `LOGS_PATH_OVERRIDE` | path | - | 日志路径覆盖（Docker 部署用） |
| `SQL_ENGINE__ENABLE_PLAN_CACHE` | bool | `true` | 启用查询计划缓存 |
| `SQL_ENGINE__PLAN_CACHE_SIZE` | int | `1000` | 缓存大小 |
| `SQL_ENGINE__SLOW_QUERY_THRESHOLD` | float | `1.0` | 慢查询阈值（秒） |

**路径派生规则**：

| 派生路径 | 计算规则 | 说明 |
|----------|----------|------|
| `resolved_sqlite_path` | `{DATA_ROOT}/metadata/metadata.sqlite` | SQLite 数据库 |
| `resolved_duckdb_path` | `{DATA_ROOT}/db/ditto.duckdb` | DuckDB 数据库 |
| `market_stock_bars_path` | `{DATA_ROOT}/market/stock/bars/daily` | 股票日线 |
| `market_etf_bars_path` | `{DATA_ROOT}/market/etf/bars/daily` | ETF 日线 |
| `market_index_bars_path` | `{DATA_ROOT}/market/index/bars/daily` | 指数日线 |
| `market_stock_adj_path` | `{DATA_ROOT}/market/stock/adj` | 股票复权因子 |
| `market_etf_adj_path` | `{DATA_ROOT}/market/etf/adj` | ETF 复权因子 |
| `market_etf_nav_path` | `{DATA_ROOT}/market/etf/nav` | ETF 净值 |
| `market_stock_status_path` | `{DATA_ROOT}/market/stock/status` | 股票状态 |
| `market_etf_status_path` | `{DATA_ROOT}/market/etf/status` | ETF 状态 |
| `capital_flow_path` | `{DATA_ROOT}/capital/flow` | 资金流 |
| `capital_margin_path` | `{DATA_ROOT}/capital/margin` | 融资融券 |
| `capital_top_board_path` | `{DATA_ROOT}/capital/top_board` | 龙虎榜 |
| `capital_limit_board_path` | `{DATA_ROOT}/capital/limit_board` | 涨跌停 |
| `capital_chip_path` | `{DATA_ROOT}/capital/chip` | 筹码分布 |
| `fundamental_financial_path` | `{DATA_ROOT}/fundamental/financial` | 财务数据 |
| `fundamental_indicator_path` | `{DATA_ROOT}/fundamental/indicator` | 财务指标 |
| `fundamental_forecast_path` | `{DATA_ROOT}/fundamental/forecast` | 业绩预告 |
| `fundamental_holding_path` | `{DATA_ROOT}/fundamental/holding` | 持股数据 |
| `macro_indicators_path` | `{DATA_ROOT}/macro/indicators` | 宏观指标 |
| `features_technical_price_path` | `{DATA_ROOT}/features/technical/price` | 技术特征（价格） |
| `features_technical_indicators_narrow_path` | `{DATA_ROOT}/features/technical/indicators_narrow` | 技术指标窄表 |
| `features_technical_indicators_wide_path` | `{DATA_ROOT}/features/technical/indicators_wide` | 技术指标宽表 |
| `factors_narrow_style_path` | `{DATA_ROOT}/factors/narrow/style` | 窄风格因子 |
| `factors_wide_style_path` | `{DATA_ROOT}/factors/wide/style` | 宽风格因子 |
| `logs_path` | `{DATA_ROOT}/logs` | 日志存储 |
| `backups_path` | `{DATA_ROOT}/backups` | 备份存储 |
| `temp_path` | `{DATA_ROOT}/temp` | 临时文件 |

### 3. data_source.env - 数据源配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `TUSHARE_TOKEN` | str | `""` | Tushare API Token（建议用 keyring） |
| `FRED_API_KEY` | str | `""` | FRED API Key（美国宏观数据，建议用 keyring） |
| `HTTP_BASE_URL` | str | `http://api.tushare.pro` | API 基础 URL |
| `HTTP_TIMEOUT` | float | `30.0` | HTTP 超时（秒） |
| `RETRY_MAX_ATTEMPTS` | int | `3` | 最大重试次数 |
| `RETRY_MULTIPLIER` | float | `1.0` | 重试间隔倍数 |
| `RETRY_MIN_WAIT` | float | `1.0` | 最小等待时间（秒） |
| `RETRY_MAX_WAIT` | float | `10.0` | 最大等待时间（秒） |
| `RATE_LIMIT_PROFILE` | str | `free` | 限流配置（`free`/`paid`） |
| `RATE_LIMIT_GLOBAL_RATE` | int | - | 全局速率限制 |
| `RATE_LIMIT_DAILY_RATE` | int | - | 每日速率限制 |
| `TDX_PATH` | str | `D:\new_tdx\vipdoc` | 通达信路径（质量对账用） |

### 4. observability.env - 可观测性配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `LOG_LEVEL` | str | `INFO` | 日志级别（`DEBUG`/`INFO`/`WARNING`/`ERROR`） |
| `LOG_FORMAT` | str | `console` | 日志格式（`console`/`json`） |
| `LOG_TO_CONSOLE` | bool | `true` | 输出到控制台 |
| `LOG_TO_FILE` | bool | `true` | 输出到文件 |
| `TRACING_ENABLED` | bool | `true` | 启用 Tracing |
| `TRACING_EXPORTER` | str | `otlp` | Tracing 导出器（`otlp`/`none`） |
| `TRACING_SAMPLE_RATE` | float | `1.0` | 采样率 |
| `METRICS_ENABLED` | bool | `true` | 启用 Metrics |
| `METRICS_EXPORTER` | str | `otlp` | Metrics 导出器 |
| `VM_ENDPOINT` | str | `http://localhost:8428/...` | VictoriaMetrics 端点 |

### 5. dq.env - 数据质量配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `L1_ENABLED` | bool | `true` | 启用 L1 检查（格式校验） |
| `L2_ENABLED` | bool | `true` | 启用 L2 检查（业务规则） |
| `L3_ENABLED` | bool | `true` | 启用 L3 检查（统计异常） |
| `RULES_DIR` | str | `config/default/dq_rules` | DQ 规则目录 |
| `QUARANTINE_ENABLED` | bool | `true` | 启用隔离区 |
| `REPORT_ENABLED` | bool | `true` | 启用报告 |
| `REPORT_PATH` | str | `data/reports/dq` | 报告路径 |

### 6. notification.env - 通知配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `EMAIL_SMTP_HOST` | str | `localhost` | SMTP 服务器 |
| `EMAIL_SMTP_PORT` | int | `587` | SMTP 端口 |
| `EMAIL_USERNAME` | str | - | SMTP 用户名 |
| `EMAIL_PASSWORD` | str | - | SMTP 密码 |
| `EMAIL_FROM` | str | `noreply@ditto.local` | 发件人地址 |
| `EMAIL_TO` | str | `""` | 收件人地址（逗号分隔） |
| `TELEGRAM_BOT_TOKEN` | str | - | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | str | - | Telegram Chat ID |
| `WECHAT_WEBHOOK_URL` | str | - | 企业微信 Webhook |
| `WECHAT_CORP_ID` | str | - | 企业微信 Corp ID |
| `WECHAT_AGENT_ID` | str | - | 企业微信 Agent ID |
| `DINGTALK_WEBHOOK_URL` | str | - | 钉钉 Webhook |
| `DINGTALK_SECRET` | str | - | 钉钉签名密钥 |
| `SLACK_WEBHOOK_URL` | str | - | Slack Webhook |
| `SLACK_CHANNEL` | str | - | Slack 频道 |
| `WEBHOOK_URL` | str | - | 通用 Webhook URL |

---

## 常用操作指南

### 添加新的配置项

**步骤**：

1. **定义配置模型**（在对应包的 `config/` 目录）

```python
# packages/data/src/ditto_data/config/data_store.py
class DataStoreSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_option: str = Field(default="default_value", description="新配置项")
```

2. **添加配置文件**（在 `config/{environment}/` 目录）

```bash
# config/development/data_store.env
NEW_OPTION=my_value
```

3. **在 ConfigProvider 中加载**（如果需要新配置文件）

```python
# interfaces/src/ditto_interfaces/registry/infra/config.py
@provide
def new_settings(self, config_loader: ConfigLoader) -> NewSettings:
    values = load_env_file(config_loader, "new_config")
    return NewSettings.model_validate(values)
```

4. **更新使用手册** ⚠️ **必须步骤**

> 新增或修改配置后，必须同步更新本文档（`docs/configuration.md`）

### 修改现有配置

**开发环境**：

```bash
vim config/development/data_store.env
# 修改后重启服务
```

**生产环境**：

```bash
vim config/production/data_store.env
# 重新部署
```

### 临时覆盖配置（环境变量）

```bash
# CLI 临时指定数据目录
DITTO_DATA_ROOT=/tmp/test_data pixi run -e dev test

# 覆盖 SQLite 路径
SQLITE_PATH=/tmp/test.db pixi run -e dev python -c "..."

# Docker 部署时覆盖日志目录
LOG_DIR=/app/logs pixi run server
```

### 切换运行环境

```bash
# 临时切换
ENVIRONMENT=testing pixi run -e dev test

# 持久设置（添加到 ~/.bashrc 或 .env）
export ENVIRONMENT=production
```

### 查看当前配置

```bash
# 查看环境
pixi run -e dev python -c "
from ditto_infra.foundation.config import get_environment
print(get_environment())
"

# 查看完整配置（需要 DI 容器）
pixi run -e dev python -c "
from dishka import make_container
from ditto_interfaces.registry.infra.config import ConfigProvider
from ditto_data.config.data_store import DataStoreSettings
import os
os.environ['ENVIRONMENT'] = 'development'
c = make_container(ConfigProvider())
s = c.get(DataStoreSettings)
print(f'DATA_ROOT: {s.data_root}')
print(f'SQLite: {s.resolved_sqlite_path}')
c.close()
"
```

### 添加新环境

1. 创建配置目录：

```bash
mkdir -p config/staging
cp config/development/*.env config/staging/
```

2. 修改配置文件：

```bash
vim config/staging/*.env
```

3. 设置环境变量：

```bash
export ENVIRONMENT=staging
```

---

## 故障排查

### 常见问题

#### 1. 配置未生效

**症状**：修改了配置文件，但运行时使用的是旧值

**排查**：

```bash
# 1. 确认环境变量
echo $ENVIRONMENT

# 2. 确认配置文件路径
ls -la config/$ENVIRONMENT/

# 3. 检查配置加载
pixi run -e dev python -c "
from ditto_infra.foundation.config import get_environment, ConfigLoader
env = get_environment()
loader = ConfigLoader(env)
print(f'环境: {env.value}')
print(f'配置目录: {loader.config_dir}')
"
```

**解决**：确保 `ENVIRONMENT` 环境变量与配置目录匹配

#### 2. 配置文件找不到

**症状**：`FileNotFoundError: config/xxx/yyy.env`

**排查**：

```bash
# 检查配置文件是否存在
ls -la config/development/
```

**解决**：确保所有配置文件都存在

#### 3. 配置验证失败

**症状**：`ValidationError: ...`

**排查**：

```bash
# 检查配置值格式
cat config/development/data_store.env | grep -v '^#' | grep -v '^$'
```

**解决**：
- 布尔值使用 `true`/`false`（小写）
- 数字不要加引号
- 嵌套配置使用 `PARENT__CHILD` 格式

#### 4. 数据目录权限问题

**症状**：`PermissionError: [Errno 13] ...`

**解决**：

```bash
# 检查目录权限
ls -la data/

# 修复权限
chmod 755 data/
```

#### 5. Token 未生效

**症状**：`Tushare API 返回认证失败`

**排查**：

```bash
# 检查 keyring 配置
pixi run -e dev python -c "
import keyring
token = keyring.get_password('tushare', 'token')
print('Token 已配置' if token else 'Token 未配置')
"

# 检查环境变量
echo $TUSHARE_TOKEN
```

**解决**：
- 确保 keyring 正确配置
- 或设置环境变量 `TUSHARE_TOKEN`

### 调试技巧

```bash
# 打印所有配置
pixi run -e dev python -c "
import os
os.environ['ENVIRONMENT'] = 'development'
from dishka import make_container
from ditto_interfaces.registry.infra.config import ConfigProvider
from ditto_infra.foundation.config.settings import Settings

c = make_container(ConfigProvider())
s = c.get(Settings)
print(s.model_dump_json(indent=2))
c.close()
"
```

---

## 附录

### 环境变量参考

| 环境变量 | 作用 | 示例 |
|---------|------|------|
| `ENVIRONMENT` | 运行时环境 | `development`, `testing`, `production` |
| `DITTO_DATA_ROOT` | 覆盖数据目录 | `/data/ditto` |
| `SQLITE_PATH` | 覆盖 SQLite 路径 | `/tmp/test.db` |
| `DUCKDB_PATH` | 覆盖 DuckDB 路径 | `/tmp/test.duckdb` |
| `LOG_DIR` | 覆盖日志目录（Docker 部署用） | `/app/logs` |
| `TUSHARE_TOKEN` | Tushare Token（优先级最高） | `your_token` |
| `FRED_API_KEY` | FRED API Key（优先级最高） | `your_api_key` |

### 配置模型清单

| 模型 | 位置 | 配置文件 |
|------|------|---------|
| `SystemSettings` | `ditto_infra/foundation/config/settings.py` | `system.env` |
| `ObservabilitySettings` | `ditto_infra/foundation/config/settings.py` | `observability.env` |
| `DataStoreSettings` | `ditto_data/config/data_store.py` | `data_store.env` |
| `DataSourceSettings` | `ditto_data/config/data_source.py` | `data_source.env` |
| `FileStorageSettings` | `ditto_data/config/` | 派生自 `DataStoreSettings` |
| `DQSettings` | `ditto_data/quality/config/` | `dq.env` |
| `NotificationSettings` | `ditto_infra/services/notification/config.py` | `notification.env` |

### 相关文档

- [架构设计规范](/.claude/rules/architecture.md)
- [Python 核心规范](/.claude/rules/python.md)
- [配置系统规范](/.claude/rules/config.md)
- [CLAUDE.md - 配置系统规范](/CLAUDE.md)
- [运维手册](/docs/ops-manual.md)
