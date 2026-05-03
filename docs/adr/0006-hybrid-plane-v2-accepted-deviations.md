# ADR 0006: Hybrid Plane v2 — 已接受的设计偏离

> **[历史参考]** 本文档记录架构演进过程中的决策，包名引用可能已过时。当前包名请参考 CLAUDE.md。

**状态**: 已接受
**日期**: 2026-04-03
**决策者**: 架构团队
**相关 ADR**: [ADR 0002](0002-monorepo-structure.md), [ADR 0004](0004-domain-layer-subdomains.md)

---

## 背景

Hybrid Plane v2 架构重构（Phase 0-5）已落地。实施过程中，7 处实现与原始设计文档存在偏离。这些偏离经评估后均为合理选择，现正式记录为已接受的架构决策。

另有 1 处未文档化的跨层依赖需补充记录。Phase F 收尾工作中新增 1 处偏离（D7）。

---

## 已接受的偏离

### D1: `interfaces/api/` 而非 `interfaces/http/`

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| 路径 | `ditto_interfaces/http/` | `ditto_interfaces/api/` |

**接受理由**：`api/` 比 `http/` 更准确地描述内容 — FastAPI routes 是 RESTful API handlers，非通用 HTTP handlers（不包含静态文件服务、WebSocket 等）。

### D2: DI 实现为分散模式，非各包 `di.py`

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| Data | 各包统一 `di.py` | Data 有 `di/` 目录，App 有 `providers.py`，Interfaces 为 Composition Root |

**接受理由**：app 层保持 DI 框架无关。`di/` 目录（Data）和 `providers.py`（App）的命名反映了不同粒度的 DI 需求 — Data 需要多个 provider 工厂，App 需要跨包的 builder 编排。统一命名反而会掩盖职责差异。

### D3: Analytics 依赖 `ditto_data.errors`（仅 2 个错误类）

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| Analytics 隔离 | 不依赖 Data | 仅 import `ditto_data.errors` 的 `DerivedNotImplementedError` |

**接受理由**：Analytics 的表达式编译器需要检测衍生因子尚未实现的情况。将这 2 个错误类移入 Kernel 会违反 Kernel "零业务行为" 原则 — 这些错误带有因子特定的语义。当前设计在 `CLAUDE.md` 和 `.importlinter` 中已记录为允许范围。

### D4: `ditto_data/provider.py` 而非 `kernel/provider.py`

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| Provider 位置 | `ditto_kernel.provider` | `ditto_data.provider` |

**接受理由**：`BarQuery` 和 `InstrumentQuery` 是数据层值对象，需要 polars 返回类型注解（`pl.DataFrame` / `pl.LazyFrame`）。Kernel 不允许 `import polars`（准入标准第 5 条），因此 Provider 必须留在 Data 层。`DataQueryProtocol` 作为纯 Protocol 接口可留在 Engine 层，与 Data 层的 Provider 实现解耦。

### D5: `packages/app/` 而非 `apps/app/`

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| App 层位置 | `apps/app/` | `packages/app/` |

**接受理由**：App 是应用编排层（CQRS），非可独立部署的应用。`apps/` 专放可部署应用（`interfaces/`、`web/`），`packages/` 放共享库。与其他 packages（engine、data、analytics）保持一致。

### D6: App 顶层扁平结构 + Registry 在 Interfaces

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| 内部结构 | `app/shared/` + `app/registry/` | 顶层扁平 CQRS（query/process/command/builders）+ registry 在 interfaces |

**接受理由**：当前体量下，`shared/` 子目录只会包含 2-3 个文件，增加目录层级反而降低导航效率。Registry 本质是 DI Composition Root，按 DI 模式应放在应用边界层（Interfaces），而非编排层（App）。

### D7: AlphaOutput/PortfolioOutput Stage 合约已删除

| 维度 | 设计文档 | 实际实现 |
|------|---------|---------|
| Stage 间合约 | `AlphaOutput(frozen=True)` + `PortfolioOutput(frozen=True)` frozen dataclass | **已删除** — engine loop 使用 `DecisionFrame`（polars DataFrame + 列名约定） |

**接受理由**：设计文档原计划用 frozen dataclass 正式化 Stage 边界数据契约（`AlphaOutput.signals` 含 instrument_id/score/rank，`PortfolioOutput.targets` 含 instrument_id/target_weight）。但这两个合约仅存在于测试代码中，从未集成到 EngineLoop 主路径。实际引擎循环通过 `DecisionFrame = pl.DataFrame` 的列名约定进行 Stage 间数据流，运行时零开销且灵活。决定：保留 DecisionFrame 列名约定作为 v2 方案，不引入 frozen dataclass 包装层。

---

## 未文档化的跨层依赖

### `ditto_platform.foundation` 在 Analysis 中的使用

**位置**：`packages/analysis/src/ditto_analysis/research/domain.py:13`

```python
from ditto_platform.foundation import logger
```

**用途**：`_apply_late_arrival_policy` 中记录晚到数据检测的 warning 日志。

**评估**：Analysis → Platform 是跨层依赖，但 Platform（技术基础设施）不包含业务逻辑，所有业务层均可安全使用。`.importlinter` 的 `analysis-isolation` 规则未将 `ditto_platform` 列为 forbidden，因此该依赖未被阻止。

**行动**：在 `CLAUDE.md` 架构原则中补充 Analysis 可依赖 Platform 的说明。当前不阻塞。

---

## 不在本 ADR 范围

| 项目 | 说明 |
|------|------|
| 39 处 "datahub" 注释残留 | 纯文档，触及文件时顺手改 |
| DI 架构重构（`di.py` → `app registry`） | 已接受当前设计（D2），功能性正确 |
| `query/contracts.py` 缺失 | 功能已在 `provider.py` 中，无需拆分 |
| AlphaOutput/PortfolioOutput contracts | 已删除（D7），引擎使用 DecisionFrame 列名约定 |

---

## 影响

无行为变更。本 ADR 仅记录已落地的事实决策，确保设计与实现的一致性。

---

**文档版本**: 1.1
**最后更新**: 2026-04-04
