> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Phase 6: 跨切面审计报告

> **日期**: 2026-04-17
> **范围**: 错误体系 + DI 体系 + 配置体系 + 测试体系
> **架构检查**: 24 条契约全部通过

---

## 1. 错误体系审计

### P0（2 项）— 异常捕获可能失败

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P0-1 | DataSourceError 同名冲突 | `sources/base.py:11` + `errors.py:279` | 两套完全不同的继承体系（Exception vs DataError）。coordinator 导入 errors.py 版本，但 tushare/fred 抛出 base.py 版本，`except` 可能捕获失败 |
| X-P0-2 | SourceFetchError 同名冲突 | `sources/base.py:109` + `errors.py:426` | 同上 |

### P1（3 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P1-1 | ValidationError 同名冲突 | `interfaces/exceptions.py:50` + `data/errors.py:214` | 两个同名异常语义不同（API 层 vs 数据层） |
| X-P1-2 | DerivedError 不继承 DataError | `data/errors.py:21` | `except DataError` 无法捕获 Derived 异常 |
| X-P1-3 | 12 个异常裸继承 Exception | 多文件 | 不纳入任何异常体系，含 6 个业务异常应归入 DataError |

### P2（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P2-1 | DittoException 没有 details dict | `interfaces/exceptions.py:6-12` | 与 DataError 的结构化错误信息不一致 |
| X-P2-2 | 部分异常 details 使用裸 str | `data/models/ingestion.py:80-164` | 3 个异常未使用 details dict 模式 |
| X-P2-3 | Engine 层缺少 errors.py | engine/ | StateTransitionError 散落在 order_book.py |
| X-P2-4 | App 层异常散落各模块 | `app/process/materialization/` | CascadeDepthExceededError、MissingDependencyError 应集中 |

### 完整异常继承树

```
Exception
├── DittoException (interfaces) → DataNotFoundError, InvalidDateError, ...
│   └── APIError → DateRangeError, NotFoundError, BadRequestError, ...
├── DataError (kernel) → CalendarError, IdentifierError, ValidationError, ...
│   └── DataSourceError (errors.py) → NetworkError, AuthError, SourceFetchError
├── DerivedError (data) → DerivedNotFoundError, DerivedVersionError, ...
├── DataSourceError (sources/base.py) → SourceConfigurationError, SourceFetchError
├── [12 个裸 Exception] → StateTransitionError, ExpressionCompileError, ...
```

**核心问题**: 3 组同名异常（DataSourceError、SourceFetchError、ValidationError）各自有不同继承链。

---

## 2. DI 体系审计

### P1（1 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P1-4 | ConfigValidationProvider 未注册 | `registry/infra/config.py:114-115` | 已实现但未加入 init_coordinator()，启动时不校验 TUSHARE_TOKEN/DATA_DIR |

### P2（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P2-5 | DQSettings 开关未被 QualityEngine 消费 | `registry/infra/config.py:199-203` | l1/l2/l3_enabled 加载但未传递给引擎 |
| X-P2-6 | App 层直接读取环境变量 | `app/providers.py:140-141` | DITTO_TRADING_CALENDAR_START/END 绕过配置体系 |
| X-P2-7 | Context 工厂创建完整容器只为取少量服务 | `registry/contexts/` | create_query_context() 创建 21 个 Provider 只取 5 个 Facade |
| X-P2-8 | Ports 模式仅 Market/Fundamental/Capital 使用 | `data/services/ports.py` | 其他域未推广 |

### P3（2 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P3-1 | RuntimeProvider 过大（35+ @provide） | `data/di/runtime.py` | 应拆分 |
| X-P3-2 | DI 遗漏累积 | 多处 | 各 Phase 发现的 8+ 个未注册 Service |

### DI 规模

- **21 个 Provider**，~170+ 个 @provide 注册点
- **Composition Root**: registry/container.py → 3 层 Provider（infra 4 + data 11 + app 6）
- **Bundle 模式**: 4 个 frozen dataclass 上下文

---

## 3. 配置体系审计

### P1（2 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P1-5 | ENVIRONMENT 未迁移到 DITTO_ENV | `infra/config/environment.py:66` | 通用名称有冲突风险 |
| X-P1-6 | DQSettings.environment 是 str 而非枚举 | `data/quality/config.py:13` | 缺少类型安全保障 |

### P2（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P2-9 | TradingSettings 定义但从未被使用 | `infra/config/settings.py:16-34` | 无对应 env 文件，ConfigProvider 未加载 |
| X-P2-10 | dq_settings 加载但未被引擎消费 | 同 X-P2-5 | 配置与运行时断裂 |
| X-P2-11 | ConfigValidationProvider 未注册 | 同 X-P1-4 | 启动不校验关键配置 |
| X-P2-12 | tdx_path 硬编码 Windows 路径 | `data/config/data_source.py:34` | `D:\new_tdx\vipdoc` 不跨平台 |

### P3（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| X-P3-3 | 三环境配置差异极小 | config/ | 可提取公共默认配置 |
| X-P3-4 | ConfigLoader 使用相对路径 | `infra/config/loader.py:24` | 依赖工作目录 |
| X-P3-5 | DataStoreSettings 缺少 fx/commodity 路径 | `data/config/data_store.py` | 路径散落硬编码 |
| X-P3-6 | observability.env 缺少环境差异化 | config/ | production 应有不同日志级别 |

### 配置层次

```
Settings (infra) → SystemSettings + ObservabilitySettings + TradingSettings
DataStoreSettings (data) → 30+ 派生路径属性
DataSourceSettings (data) → HTTP/retry/rate_limit/token
DQSettings (data) → L1/L2/L3 开关 + 规则目录
NotificationSettings (infra) → SMTP/Telegram/Webhook
```

---

## 4. 测试体系审计

### 测试规模

| 指标 | 数值 |
|------|------|
| 测试用例 | 5,503 passed, 25 skipped |
| 执行时间 | 40.14s（并行） |
| 覆盖率门槛 | 80% 分支覆盖（CI 强制） |
| mock 使用 | 186 文件, 441 处 |
| pytest.raises | 215 文件 |

### P1（2 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| T-P1-1 | 5 个 unit 测试文件放在 integration/ 目录 | `interfaces/tests/integration/api/test_*_router_unit.py` | 使用 mock 的 FastAPI TestClient 测试应移至 unit/ |
| T-P1-2 | 单元测试文件命名为 integration | `app/tests/unit/process/execution/test_factor_backtest_integration.py` | 实际使用 MagicMock，应重命名 |

### P2（6 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| T-P2-1 | ~130+ 测试文件缺少 `_unit` 后缀 | 所有 `tests/unit/` | 28% 的单元测试未遵循命名规范 |
| T-P2-2 | kernel 包 6 个模块完全无测试 | `packages/kernel/` | exceptions, specs, quality, research, types, math |
| T-P2-3 | infra notification 4 个文件无测试 | `packages/infra/services/notification/` | business, email, config, manager |
| T-P2-4 | init_observability autouse fixture 无 teardown | `packages/data/tests/conftest.py:40-52` | 可观测性全局状态可能泄露 |
| T-P2-5 | 大量 storage reader/writer 缺少测试 | `packages/data/storage/` | market/etf/index 多个 reader/writer 无对应测试 |
| T-P2-6 | analytics 编译器子模块缺少独立测试 | `packages/analytics/expression/` | 仅通过顶层集成测试间接覆盖 |

### P3（7 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| T-P3-1 | fake_time fixture 重复定义 | interfaces + data conftest | 完全相同实现 |
| T-P3-2 | FRED client 网络错误测试未标记 slow | `data/tests/unit/sources/fred/` | 耗时 4.02s |
| T-P3-3 | AAA 模式仅在 2 个文件中使用 | — | 其余 470+ 文件无显式注释 |
| T-P3-4 | 少量直接 SQLite 连接绕过 fixture | 4 个文件 | 未通过 sqlite_pool fixture |
| T-P3-5 | slow/serial marker 定义但极少使用 | pyproject.toml | 长时间测试拖慢 CI |
| T-P3-6 | cli_test marker 未在 markers 列表声明 | interfaces/conftest.py | 与 strict-markers 冲突风险 |
| T-P3-7 | MagicMock 替代 Slice 真实数据结构 | `app/tests/unit/process/execution/` | 降低测试真实性 |

### 测试体系评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **覆盖率** | 8/10 | 5503 用例 + 80% CI 门槛 + 分支覆盖，但 kernel/infra 有盲区 |
| **分层** | 8/10 | unit/integration/e2e 清晰，5 个文件放错目录 |
| **命名** | 7/10 | 28% 缺少 `_unit` 后缀，1 个命名与实际不符 |
| **隔离** | 9/10 | tmp_path/monkeypatch/内存数据库，autouse fixture 缺 teardown |
| **配置** | 9/10 | 7 个 marker + filterwarnings=error + xdist 并行 |

---

## 全审计汇总统计

| Phase | P0 | P1 | P2 | P3 | 合计 |
|-------|----|----|----|----|----|
| 1. Kernel + Infra | 0 | 3+3 | 4+2 | 3+3 | 18 |
| 2. Data | 0 | 10 | 10 | 9 | 29 |
| 3. Analytics + Engine | 0 | 3+2 | 7+5 | 4+6 | 27 |
| 4+5. App + Interfaces | 0 | 5+1 | 4+13 | 3+9 | 35 |
| 6. 跨切面 | 2 | 5 | 12 | 13 | 32 |
| **总计** | **2** | **34** | **55** | **47** | **138** |

### P0 修复优先级

1. **DataSourceError/SourceFetchError 同名冲突** — 可能导致异常捕获失败（X-P0-1, X-P0-2）
2. 无其他 P0 级问题

### Top 5 P1 修复建议

1. 异常同名冲突消解（3 组同名异常）
2. DerivedError 纳入 DataError 体系
3. ConfigValidationProvider 注册到启动流程
4. 各层 DI 注册遗漏修复（8+ Service）
5. ENVIRONMENT → DITTO_ENV + DQSettings 类型统一
