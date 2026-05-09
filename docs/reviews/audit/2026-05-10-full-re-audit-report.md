# Ditto 全模块重审报告

> 日期：2026-05-10
> 基线：`docs/plans/2026-05-08-module-by-module-review-plan.md`（原始 12 模块审计）
> 触发：B1-B7 跨模块整改已合入 `remediation/cross-module-b1-b7` 分支，需基于最新源码重新评估
> 方法：7 个并行代理逐模块审计，六维度评分（1-5 分），三档优先级（P0/P1/P2）
> 验证：`arch-check 36/36 kept`，`arch-smells passed`，6319 tests passed

---

## 1. 执行摘要

### 1.1 B1-B7 修复效果

| 批次 | 核心目标 | 修复项数 | 状态 |
|------|---------|---------|------|
| B1 | 卫生治理 — 虚假依赖清除、SQL 安全加固、文档同步 | 10 | ✅ 全部完成 |
| B2 | 公共 API 收敛 — barrel 扩展、深层引用消除、`__all__` 纪律 | 12 | ✅ 全部完成 |
| B3 | Protocol 归位 — 接口断裂修复、冗余清理、命名消歧 | 8 | ✅ 全部完成 |
| B4 | 事件类型化 — EventName 常量类、RiskGuardDetails typed payload | 6 | ✅ 全部完成 |
| B5 | 状态恢复 — PortfolioStateSnapshot、MaxDrawdownRule snapshot、StrategyContext snapshot、Replay 扩展 | 6 | ✅ 全部完成 |
| B6 | 大文件拆分 — ParquetStore/planner/providers/statistics/routes 拆分 | 12 | ✅ 全部完成 |
| B7 | 成熟度标注 — 模板/路由/数据集成熟度诚实化 | 6 | ✅ 全部完成 |

**B1-B7 总计修复 60 个 finding**。

### 1.2 重审后全局评分

| 模块 | 源码 LOC | 测试 LOC | 综合评分 | 趋势 |
|------|---------|---------|---------|------|
| kernel | 1,522 | 2,798 | **4.0/5** | → 稳定 |
| platform | 5,724 | ~5,800 | **4.2/5** | ↑ (拆分+SQL安全) |
| portfolio | 1,724 | 2,575 | **3.8/5** | → 稳定 |
| risk | 1,372 | 2,103 | **4.2/5** | ↑ (B3清理+B4类型化+B5快照) |
| execution | 3,064 | 5,571 | **3.9/5** | ↑ (B3+B6拆分) |
| strategy | 5,485 | 8,566 | **4.0/5** | ↑ (B6拆分+B5快照+B7成熟度) |
| analysis | 1,121 | 1,794 | **4.7/5** | ↑ (B7 reserved强化) |
| features | 14,716 | 8,789 | **4.2/5** | ↑ (time semantics修复) |
| backtest | 5,002 | 17,185 | **4.2/5** | ↑ (B5 replay+B6拆分) |
| data | 30,651 | 39,695 | **3.4/5** | → 稳定 |
| application | 18,296 | ~18,000 | **3.9/5** | ↑ (B6 providers拆分) |
| apps | 12,286 | ~17,000 | **4.0/5** | ↑ (B6 routes拆分+B7成熟度) |

**全局均分：4.0/5**（原审计无统一评分，但各维度可见明显改善）

### 1.3 剩余问题统计

| 类别 | 数量 | 说明 |
|------|------|------|
| P0（阻断） | **1** | kernel 3 个领域泄漏文件（原 P0 未修复）+ application default slippage 不一致 |
| P1（代码级） | **24** | 跨层穿透、死代码、接口不一致 |
| P1（架构级） | **12** | OMS Lite、Runtime Spine、Consumer-Owned Ports |
| P2（建议） | **30+** | 命名微调、文档同步、测试补强 |

---

## 2. 逐模块审计摘要

### 2.1 Kernel（评分 4.0/5）

**已修复**：B4 EventName 常量类已添加（5 个事件常量）；DomainEvent 兼容策略已文档化；barrel `__all__` 30 符号完整且所有叶模块均有定义。

**未修复（P0 级，3 项原报告遗留）**：
- `publication_safety.py`（233 行）仍留在 kernel，features 领域泄漏
- `quality.py`（105 行）仍留在 kernel，data 领域泄漏
- `research.py`（79 行）仍留在 kernel，analysis 领域泄漏

**未修复（P1 级）**：
- `strategy.py` DerivedSpec/DerivedRole → features
- `trading.py` A 股业务常量 → execution/backtest
- `json_types.py` → platform.foundation
- `exceptions.py` DerivedError 层级 → features
- `market.py` MacroDataProvider → data

**架构级**：K-ARCH-2 市场规则默认值散落、K-ARCH-3 DerivedError 归属模糊均未修复。

**新发现**：
- `strategy.py` 中 DecisionFrame Protocol 无运行时 schema 校验
- `trading.py` BrokerProtocol 零外部消费者（死 Protocol）

**建议**：kernel 原报告 3 个 P0 是最高优先级迁移项，应在下一轮整改首批发力。

---

### 2.2 Platform（评分 4.2/5）

**已修复**：
- PL-2 SQL 标识符注入：`validate_identifier()` 已添加，`table` 参数全面校验
- PL-3 ParquetStore 769 行 → 拆分为 6 个模块（352+73+141+46+66+146），效果优秀
- PL-ARCH-1 通用存储领域术语：已完全清除
- PL-ARCH-2 SQL/noqa：从分散收归至 2 处合理点

**大部分修复**：
- PL-1 深层引用：barrel 扩展至 55+ 符号，95% 引用已收敛，仅 3 处残留

**未修复**：
- PL-4 paths.py 废弃函数：功能上已废弃（抛 RuntimeError），但 24 行死代码仍在
- PL-9 metrics.py 534 行：未拆分，仍在可接受范围

**新发现**：
- [P1] `SQLiteClient.count()` 的 `where` 参数直接拼接 SQL（`table` 已校验但 `where` 未校验）

**建议**：`where` 参数安全性是唯一 P1，其余均为 P2 可延后。

---

### 2.3 Portfolio（评分 3.8/5）

**已修复**：
- PF-0 RebalanceTarget/TargetPortfolio 命名冲突（B3 删除投机性 DTO）
- PF-3 barrel 导出（accounting/rebalancing 子模块 `__init__.py` 完善）
- PF-ARCH-1 状态快照（B5 `PortfolioStateSnapshot` + `FillProjector` + `AccountProjector`，7 个测试）

**未修复（P1 级）**：
- PF-1 `Account.positions` 裸 dict 暴露，无防御性保护
- PF-2 `apply_fill()` 两步非原子操作（持仓+现金），异常可致状态不一致
- PF-4 `PortfolioStateReader` Protocol 零生产消费
- PF-5 `StateTransitionError` 双路径导出

**新发现**：
- [P2] 顶层 `ditto_portfolio/__init__.py` 为空（仅 docstring）
- [P2] `Constraint` Protocol 含 `priority` property（排序策略不应入 Protocol）
- [P2] `report_views.py` 3 个 Protocol 无显式实现者（duck typing 隐式满足）

**建议**：`apply_fill()` 原子性（PF-2）是运行时一致性风险，优先修复。

---

### 2.4 Risk（评分 4.2/5）

**已修复**：
- RK-1 contracts.py 冗余 Protocol（B3 清理，现为空文件）
- RK-5 虚假依赖（B1 清除 polars/orjson）
- RK-ARCH-2 有状态快照（B5 `DrawdownStateSnapshot` + snapshot/restore，5 个测试）
- RK-ARCH-3 事件载荷类型化（B4 `RiskGuardDetails` typed dataclass）

**未修复（P1 级）**：
- RK-2 `constraints/checks.py` 319 行三层混合（Protocol + 6 Check + Composite）
- RK-3 `models.py` 三个模型完全未使用（`RiskMetrics`/`ExposureData`/`DrawdownStats`）
- RK-4 `_accept()` helper 在两处重复定义
- RK-ARCH-1 缺少统一 Risk Gate 契约

**新发现**：
- [P2] `RiskGuardTriggered.severity` 为 `str` 而非 `RiskSeverity` enum
- [P2] `RiskAction.target_quantity` 从未被填充
- [P2] `observability/__init__.py` barrel 为空

**建议**：checks.py 拆分 + `_accept()` 提取成本最低、收益最高。

---

### 2.5 Execution（评分 3.9/5）

**已修复**：
- EX-1 TradeAuditor Protocol 完善（B3 补全 3 个方法）
- EX-2 planner 530 行拆分（B6 → 7 模块，planner.py 降至 164 LOC）

**未修复（P1 级）**：
- EX-3 TradeService 跨层穿透（application 6 处直接 import SQLite 实现类）
- EX-4 FillStore/FillReceiver/TradeService.save_fill 三重接口重叠

**未修复（架构级）**：
- EX-ARCH-1 OMS 身份与 journal 缺失（Known Gap）
- EX-ARCH-2 四张表无统一关联键（Known Gap）
- EX-ARCH-3 BrokerGateway 无具体适配器（Known Gap）
- EX-ARCH-4 市场规则语义散落（部分缓解）

**新发现**：
- [P1] TradeAuditor Protocol `Sequence[T]` vs 实现 `tuple[T, ...]` 签名不一致
- [P2] `__init__.py` 导出为空（`__all__ = []`）
- [P2] `compute_diff` 10 个参数过多
- [P2] CLAUDE.md planner 描述仍写 530 LOC（实际 164 LOC），严重过时

**建议**：TradeAuditor 签名统一（1 行改动 ×3）+ CLAUDE.md 更新是速赢项。

---

### 2.6 Strategy（评分 4.0/5）

**已修复**：
- ST-2 stock_sector_rotation.py 640 行拆分（B6 → stages + config + 入口）
- ST-4 contracts.py Protocol 方法名对齐（B3）
- ST-ARCH-2 StrategyContext snapshot/restore（B5，6 个测试）
- ST-ARCH-3 模板成熟度标注（B7 ETF=initial-focus, stock=experimental）

**未修复（P1 级）**：
- ST-1 存储层跨层穿透（application **24 处**直接引用 SQLite，较原报告 21 处恶化）
- ST-3 Benchmark 白名单硬编码 A 股
- ST-5 辅助函数重复（`_utc_now()` 两处、`_raise_config_error()` 两处）

**新发现**：
- [P1] `StrategyCatalogReaderProtocol`（services 内）与 `StrategyCatalogReader`（包级 contracts）方法名不匹配
- [P1] `stock_selection_trend.py` 343 行偏大
- [P2] ETF 模板缺少 `validate_config` + `get_param_constraints`
- [P2] `MarketState`/`Signal` 模型无使用痕迹

**建议**：跨层穿透（ST-1）是最大架构债务，需将 Protocol 提升到包级 + DI 注册。

---

### 2.7 Analysis（评分 4.7/5）— 全库最佳

**已修复**：
- AN-1 Reserved namespace guard 完善（CLAUDE.md + `__init__.py` + honesty test）
- AN-ARCH-2 SHIFT late-arrival policy 标注 reserved（B7）
- AN-ARCH-3 Research v1 能力边界标注

**维持设计**：
- AN-2 Public API 极窄（3 符号）— 设计选择，CLAUDE.md 已说明

**新发现**：
- [P2] contracts.py Protocol 未标注 `@runtime_checkable`（与 strategy 包不一致）
- [P2] root barrel 极度保守（`SpineSpec`/`SpineSnapshot` 等常用类型需深层导入）

**建议**：几乎无改进空间，是全库质量标杆。

---

### 2.8 Features（评分 4.2/5）

**已修复**：
- FEAT-ARCH-2 Time semantics：codegen 层统一 `shift(1)` 策略 + golden data 测试覆盖
- FEAT-ARCH-3 表达式前瞻泄漏：`test_operator_golden_data.py` 标准测试模板（17 个操作符）

**未修复**：
- FEAT-ARCH-1 制品溯源：缺少 Polars 操作符版本追踪（仅追踪库版本）
- FEAT-3 services 命名空间：`__init__.py` re-export 44 符号，过于宽泛

**新发现**：
- [P1] `evaluation/evaluator.py`（746 LOC）混合 Protocol 定义与编排逻辑
- [P2] `codegen.py`（749 LOC）虽职责分区良好但单文件仍大

**建议**：evaluator Protocol 提取是唯一 P1，其余 P2。

---

### 2.9 Backtest（评分 4.2/5）

**已修复**：
- BT-2 大文件拆分（B6 statistics/engine/manifest 全部 < 500 LOC）
- BT-ARCH-3 Replay 覆盖（B5 扩展到 fill + account state 级别）

**未修复**：
- BT-ARCH-1 Runtime step chain 为 backtest 独有（`TradingLoop` Protocol 空洞）
- BT-ARCH-2 直接依赖 data 层 DataProvider（1 个导入点，已最小化）

**新发现**：
- [P2] `EngineMode.LIVE` 死代码（未使用的枚举值）

**建议**：backtest 质量显著提升，剩余问题均为中长期架构项。

---

### 2.10 Data（评分 3.4/5）— 全库最大改进空间

**已修复**：
- DATA-3 SQL 插值 noqa：21 处全部标注 + 安全说明注释

**未修复（架构级 P1）**：
- DATA-ARCH-1 DataCatalog/Lineage 仅 Protocol 无实现
- DATA-ARCH-2 Dataset enum（23 成员）仍是路由 spine
- DATA-ARCH-3 DataProvider 被跨包直接 import（backtest/application）
- DATA-ARCH-4 市场参考数据归属分散（部分改善）

**新发现**：
- [P1] Catalog/Lineage Protocol 零运行时验证
- [P2] `errors.py` 606 LOC 错误层级过于集中
- [P2] apps 层直接导入 12 个 data 具体服务类
- [P2] 10 个文件超 500 LOC（最大 tushare_source.py 777）

**建议**：Data 是全库最大包（70K LOC），架构抽象层（Catalog/Dataset/Provider）需要系统性投资。

---

### 2.11 Application（评分 3.9/5）

**部分修复**：
- APP-P1-01 providers 拆分（B6 → facade + 6 子模块，LOC 从 563 降至 48）

**未修复（P1 级）**：
- APP-P1-02 Runtime builder 仍定义生命周期默认值
- APP-P1-03 INGESTION_SPECS 与 data Dataset 双源事实
- APP-P1-04 Research 路径直接依赖 analysis/data/features
- APP-P2-01 8 个文件超 500 行（coordinator 764、runtime_builder 626、config 614）

**新发现**：
- [P0] `runtime_builder.py` 中 `_DEFAULT_SLIPPAGE_BPS = 5.0` 与全项目其他位置 `1.0` 不一致，可能导致回测结果 5 倍偏差
- [P1] 异常入口不统一（`DittoError` 子类 vs 裸 `ValueError`/`RuntimeError`）

**建议**：`_DEFAULT_SLIPPAGE_BPS` 不一致是 P0，应立即修复。

---

### 2.12 Apps（评分 4.0/5）

**已修复**：
- APPS-P2-01 routes 拆分（B6 backtest 526 → facade 47 + run_routes + query_routes；trade 412 → facade 43 + 子模块）
- APPS-P1-02 maturity-aware API（B7 9 个路由添加成熟度 docstring）

**未修复（P1 级）**：
- APPS-P1-01 E2E 测试跳过机制掩盖核心路径（25 个 skip）
- APPS-P1-03 Registry composition 可能积累业务事实

**建议**：committed synthetic golden E2E lane 是最高优先级。

---

## 3. 跨模块统一治理

### 3.1 代码级治理（原报告剩余 + 新发现）

| 治理项 | 影响范围 | 优先级 | 状态 |
|--------|---------|--------|------|
| Kernel 领域泄漏 3 文件迁移 | kernel → features/data/analysis | **P0** | 未修复 |
| 跨层穿透（application→storage） | strategy(24) + execution(6) + data(12) | **P1** | 未修复 |
| 三重 save_fill 接口合并 | execution | **P1** | 未修复 |
| TradeAuditor 签名统一 | execution | **P1** | 新发现 |
| 死代码/模型清理 | risk(models) + strategy(MarketState/Signal) + platform(paths) | **P1** | 未修复 |
| checks.py 拆分 + _accept 提取 | risk | **P1** | 未修复 |
| _DEFAULT_SLIPPAGE_BPS 不一致 | application runtime_builder | **P0** | 新发现 |
| Service 后缀语义收敛 | 全局 | P2 | 未修复 |
| `__all__` / barrel 统一 | execution(空) + portfolio(空) | P2 | 未修复 |
| CLAUDE.md 过时 | execution + strategy | P2 | 未修复 |

### 3.2 架构级治理（中长期）

| 治理项 | 来源 | 前置条件 | 优先级 |
|--------|------|---------|--------|
| Runtime Spine（事件/时间/状态统一） | BT-ARCH-1, EX-ARCH-1, RK-ARCH-1 | 无 | **P0** |
| OMS Lite（身份/journal/状态机） | EX-ARCH-1~4 | Runtime Spine | **P0** |
| Consumer-Owned Ports | BT-ARCH-2, DATA-ARCH-3, APP-P1-01 | Runtime Spine | P1 |
| DataCatalog Runtime | DATA-ARCH-1, FEAT-ARCH-1 | Consumer-Owned Ports | P1 |
| 状态快照/恢复（portfolio 发射事件） | PF-ARCH-3 | OMS Lite | P1 |
| 市场参考 Provider ADR | DATA-ARCH-4, K-ARCH-2, EX-ARCH-4 | OMS Lite | P1 |
| Golden E2E Lane | APPS-P1-01 | 无 | **P1** |

### 3.3 治理依赖图（更新版）

```
B1-B7 已完成 ✅
  │
  ├─→ [立即] P0 修复
  │    ├─ kernel 3 文件迁移
  │    └─ _DEFAULT_SLIPPAGE_BPS 统一
  │
  ├─→ [Sprint 内] P1 代码级清理
  │    ├─ 跨层穿透收敛（strategy/execution/data）
  │    ├─ 三重 save_fill 合并
  │    ├─ TradeAuditor 签名统一
  │    ├─ 死代码清理（risk models/strategy MarketState/platform paths）
  │    └─ risk checks.py 拆分
  │
  ├─→ [Sprint 内] Golden E2E Lane
  │
  ├─→ [中期] Runtime Spine 设计
  │    ├─→ OMS Lite
  │    ├─→ Consumer-Owned Ports
  │    ├─→ DataCatalog Runtime
  │    ├─→ 状态快照完整化
  │    └─→ 市场参考 Provider
  │
  └─→ [持续] P2 清理
       ├─ CLAUDE.md 同步
       ├─ barrel/__all__ 统一
       ├─ evaluator 拆分
       └─ 大文件持续拆分
```

---

## 4. 建议的下一轮整改批次

### B8：紧急修复（P0，零前置依赖）

| 项 | 改动 | 风险 |
|----|------|------|
| kernel 领域泄漏 | 迁移 `publication_safety.py` → features、`quality.py` → data、`research.py` → analysis | 中（大量 import 需更新） |
| slippage 默认值 | 统一 `_DEFAULT_SLIPPAGE_BPS = 1.0` | 低（1 行改动） |

### B9：代码级清理（P1，零前置依赖）

| 项 | 改动 | 风险 |
|----|------|------|
| 跨层穿透收敛 | strategy/execution Protocol 提升 + DI 注册 | 中 |
| TradeAuditor 签名 | `Sequence[T]` → `tuple[T, ...]` | 低 |
| risk 死代码 | 删除 models.py 未使用类 | 低 |
| risk checks.py 拆分 | Protocol + Check + Composite 分离 | 低 |
| _accept 提取 | 共享 helper | 低 |

### B10：Golden E2E + 文档同步

| 项 | 改动 | 风险 |
|----|------|------|
| committed synthetic golden E2E | 小型确定性数据集覆盖完整链路 | 中 |
| CLAUDE.md 同步 | execution/strategy/platform 更新 | 低 |
| 三重 save_fill 合并 | execution 接口统一 | 中 |

---

## 5. 各模块详细审计报告索引

| 模块 | 评分 | 详细报告位置 |
|------|------|-------------|
| kernel | 4.0 | 本文件 §2.1 |
| platform | 4.2 | 本文件 §2.2 |
| portfolio | 3.8 | 本文件 §2.3 |
| risk | 4.2 | 本文件 §2.4 |
| execution | 3.9 | 本文件 §2.5 |
| strategy | 4.0 | 本文件 §2.6 |
| analysis | 4.7 | 本文件 §2.7 |
| features | 4.2 | 本文件 §2.8 |
| backtest | 4.2 | 本文件 §2.9 |
| data | 3.4 | 本文件 §2.10 |
| application | 3.9 | 本文件 §2.11 |
| apps | 4.0 | 本文件 §2.12 |

> 各模块的完整六维度评分、逐文件检查结果、新发现问题详见并行代理原始报告。
