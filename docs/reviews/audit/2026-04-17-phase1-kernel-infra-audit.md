# Phase 1: Kernel + Infra 审计报告

> **日期**: 2026-04-17
> **范围**: packages/kernel (11 文件, 899 行) + packages/infra (48 文件, 4,518 行)
> **架构检查**: 24 条契约全部通过

---

## Kernel 审计发现

### P0 — 无

### P1 — 架构违规 / 职责错位

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| K-P1-1 | `L3CheckResult`/`ReconciliationResult` 不属于 Kernel | `quality.py:110-161` | 仅被 app 包使用，代码注释明确标注"临时"（`patrol.py:28`），不满足"≥2 业务包消费"准入标准 |
| K-P1-2 | `RiskScope` 仅被 engine 使用 | `enums.py:81-85` | 不满足准入标准，应移至 `ditto_engine` |
| K-P1-3 | `MacroCategory`/`MacroFrequency` 仅被 data 使用 | `enums.py:88-123` | 不满足准入标准，应移至 `ditto_data` |

### P2 — 命名 / 风格

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| K-P2-1 | `ImpactModel` 未从 `__init__.py` re-export | `enums.py:24`, `__init__.py` | 消费者必须 `from ditto_kernel.enums import`，绕过顶层 API |
| K-P2-2 | `ReconciliationResult.to_dict()` 含序列化逻辑 | `quality.py:149-161` | 违反 Kernel "纯值语义/不含序列化" 红线 |
| K-P2-3 | `DataError` 命名暗示 Data 层概念 | `exceptions.py:21` | 放在 Kernel 中语义矛盾 |
| K-P2-4 | `CALENDAR_TO_TIMEZONE`/`GRAIN_TO_TIME_KEYS` 无外部消费者 | `specs.py:48-55`, `__init__.py:47-48` | 不应 re-export 仅内部使用的常量 |

### P3 — 可改进

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| K-P3-1 | `InstrumentId = NewType(...)` 运行时无类型安全 | `identity.py:11` | 多个消费者使用 `as _InstrumentId` 别名暗示冲突 |
| K-P3-2 | `math.py` 仅含单函数 `pearson_correlation` | `math.py` | 可考虑标准库 `statistics.correlation` (3.10+) |
| K-P3-3 | CLAUDE.md 引用不存在的 `interfaces` 包作为消费者 | CLAUDE.md | 文档与实际不符 |

### Kernel 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 8/10 | 零行为原则整体遵守，Protocol 薄实现合规，但有 3 个类型不满足准入标准 |
| **抽象** | 8/10 | 类型设计合理，Protocol 定义遵循零实现原则，命名有少量不一致 |
| **依赖** | 10/10 | 零外部依赖，importlinter 全部通过 |
| **实践** | 9/10 | 类型标注完整，代码简洁，仅 `to_dict()` 序列化越界 |

---

## Infra 审计发现

### P0 — 无

### P1 — 架构违规 / 职责错位

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| I-P1-1 | Data 层目录结构硬编码在 Infra | `config/providers/data_root.py:79-121` | 30+ 个业务目录路径硬编码，Data 层新增目录需同步修改 Infra |
| I-P1-2 | 业务特定校验逻辑泄漏 | `config/providers/config_validation.py:44-47` | `TUSHARE_TOKEN` 校验属于 Data 层职责 |
| I-P1-3 | 数据集元数据泄漏 | `util/checksum.py:35-47` | `SORT_KEYS` 包含 Data 层特定数据集排序规则 |

### P2 — 命名 / 风格

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| I-P2-1 | 通知服务业务逻辑泄漏 | `services/notification/business.py:14-98` | `alert_dq_failure`/`alert_ingestion_failure` 绑定特定业务场景，含业务判断逻辑 |
| I-P2-2 | Logger 导入路径不统一 | 8 个文件 | 绕过 foundation 公共 API 直接 `from loguru import logger` |

### P3 — 可改进

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| I-P3-1 | 文档语言不一致 | notification 模块 | 中英文混用 |
| I-P3-2 | Metrics 类包含业务指标名 | `observability/metrics.py:57-256` | `factor_ic`、`portfolio_drawdown` 等业务指标，但作为注册表设计合理 |
| I-P3-3 | tracing 模块全局可变状态 | `observability/tracing.py:56` | 已被 `reset_for_testing()` 封装，风险可控 |

### Infra 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 7/10 | foundation/services 分层合理，但 3 处 Data 层领域知识泄漏违反 "零领域概念" 原则 |
| **抽象** | 8/10 | 接口设计清晰（SQLitePool/Client 组合、NotificationSender ABC），配置层次合理 |
| **依赖** | 9/10 | 无代码级跨包依赖，但 data_root.py/config_validation.py/checksum.py 存在隐式语义耦合 |
| **实践** | 9/10 | 类型标注完整（ParamSpec, TypeGuard, 泛型），无禁止依赖，错误处理模式一致 |

---

## 业界对标总结

### Kernel
- **优于 LEAN** `Common/` (~100 文件)：Ditto Kernel 11 文件更纯粹
- **优于 NautilusTrader** `nautilus_model/`：无语言绑定复杂度
- **待改进**：准入标准执行不严（3 个类型不满足 ≥2 包消费）

### Infra
- **符合 Hexagonal Architecture**：Infra 实现技术关注点
- **符合 OpenBB 微内核理念**：零 provider 依赖
- **待改进**：3 处领域知识泄漏需迁移至 Data 层
