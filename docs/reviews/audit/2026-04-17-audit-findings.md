# Ditto 全维度架构审计 — 综合发现清单

> **日期**: 2026-04-17
> **审计范围**: 全部 7 个包，自底向上 6 Phase
> **总发现**: 138 项（P0: 2, P1: 34, P2: 55, P3: 47）
> **架构检查**: 24 条契约全部通过

---

## P0 — 必须立即修复（2 项）

| ID | 问题 | 位置 | 影响 |
|----|------|------|------|
| X-P0-1 | DataSourceError 同名冲突 — `sources/base.py` (继承 Exception) vs `errors.py` (继承 DataError) | data/sources/base.py:11 + data/errors.py:279 | coordinator `except SourceFetchError` 可能捕获失败 |
| X-P0-2 | SourceFetchError 同名冲突 — 同上 | data/sources/base.py:109 + data/errors.py:426 | source 抛出的异常不会被 app 层捕获 |

---

## P1 — 应尽快修复（34 项）

### 错误体系（5 项）
- X-P1-1: ValidationError 同名冲突（interfaces vs data）
- X-P1-2: DerivedError 不继承 DataError
- X-P1-3: 12 个异常裸继承 Exception
- D-P1-3: DataSourceError 重复定义（同 X-P0-1）
- D-P1-4: SourceFetchError 重复定义（同 X-P0-2）

### 架构违规（8 项）
- D-P1-1: ExecutionAuditService 绕过 storage 层直接操作 SQLite
- D-P1-2: Trade Writer 混合读写（CQRS 违规）
- D-P1-6: importlinter data-storage-no-model-import 规则形同虚设
- I-P1-1~3: Infra 硬编码 Data 层目录结构/校验/排序键
- K-P1-1: L3CheckResult/ReconciliationResult 仅被 app 使用（临时安排）
- A-P1-2: expression ↔ materialization 循环语义依赖

### DI 注册遗漏（10 项）
- D-P1-7~9: ArtifactPersistenceService/BacktestArtifactReader/InstrumentRuleProvider 未注册
- AP-P1-2~5: ReconcileSourcesHandler/IngestDateHandler/FactorEvaluationFacade/DeliveryRouter 未注册
- X-P1-4: ConfigValidationProvider 未注册到启动流程

### 数据源/类型（5 项）
- D-P1-5: TdxSource 未继承 DataSource 基类
- D-P1-10: 缺少跨数据源 fallback/降级机制
- K-P1-2~3: RiskScope/MacroCategory/MacroFrequency 不满足 Kernel 准入标准
- A-P1-1: obv_ma20 缺少对 obv 的 dependency 声明（语义错误）

### 配置（3 项）
- X-P1-5: ENVIRONMENT 未迁移到 DITTO_ENV
- X-P1-6: DQSettings.environment 是 str 而非枚举

### 测试（2 项）
- T-P1-1: 5 个 unit 测试文件放在 integration/ 目录
- T-P1-2: 单元测试文件命名为 integration

### 命名（1 项）
- AP-P1-1: CancelRunHandler/RetryRunHandler 未使用 Command DTO

---

## P2 — 应计划修复（55 项）

### Data 层（10 项）
- D-P2-1~2: Dataset 枚举/InstrumentIdRange 含业务逻辑
- D-P2-3: RuntimeProvider 475 行
- D-P2-4: Ports 模式使用不一致
- D-P2-5: MetadataService Universe 方法绕过子服务
- D-P2-6: DataProvider Protocol 方法不完整
- D-P2-7: ParquetStore/SQLiteStore merge 代码重复
- D-P2-8: SQLiteStore/SQLiteClient 职责重叠
- D-P2-9: FredSource 约 20 个 NotImplementedError
- D-P2-10: Query 模型定义位置分散

### Interfaces 层（13 项）
- IF-P2-1~5: trade.py 业务逻辑泄漏、backtest.py 辅助函数过多、source.py 异常处理、返回裸 dict、内联模型
- IF-P2-6~7: _KNOWN_DATASETS 3 处重复、ops.py 格式化逻辑
- IF-P2-8~10: eod_flow 硬编码、backtest Flow 反序列化、dq_batch 222 行编排
- IF-P2-11: backtest 模型硬编码成本常量
- IF-P2-12~13: re-export 遗漏

### Analytics 层（7 项）
- A-P2-1~2: analyzer 依赖 contracts、lookback 隐式耦合
- A-P2-3~5: 因子分类重叠（alpha/momentum/fundamental）
- A-P2-6: research/domain.py 含数据处理逻辑
- A-P2-7: validate.py bare Exception

### Engine 层（5 项）
- E-P2-1: Order.created_at 硬编码 datetime(2026,1,1)
- E-P2-2: OrderCanceled/PositionChanged 事件未发布
- E-P2-3: _execute_delayed_signal 吞掉所有异常
- E-P2-4: _SliceView Protocol 使用 Any
- E-P2-5: AssertionError 误用

### App 层（4 项）
- AP-P2-1~2: coordinator.py/helpers.py 过大
- AP-P2-3: patrol.py 直接依赖 query Facade 类
- AP-P2-4: command/__init__.py re-export 18 个符号

### Infra 层（2 项）
- I-P2-1: notification/business.py 业务逻辑泄漏
- I-P2-2: Logger 导入路径不统一

### Kernel 层（4 项）
- K-P2-1~4: ImpactModel 未 re-export、to_dict() 序列化越界、DataError 命名矛盾、内部常量不应导出

### 跨切面（10 项）
- X-P2-1~4: DittoException 无 details dict、异常用裸 str、Engine 缺 errors.py、App 异常散落
- X-P2-5~8: DQSettings 未消费、App 直接读环境变量、Context 工厂过重、Ports 推广不一致
- X-P2-9~12: TradingSettings 未使用、dq_settings 断裂、ConfigValidation 未注册、tdx_path 硬编码

### 测试（6 项）
- T-P2-1~6: 命名不一致、kernel 无测试、notification 无测试、autouse 无 teardown、storage 缺测试、编译器缺独立测试

---

## P3 — 可改进（47 项）

各 Phase 的 P3 发现已在分报告中详列。主要类别：命名不一致（8）、类型弱化（6）、文档/注释（5）、重复代码（5）、测试质量（7）、配置细节（6）、其他（10）。

---

## 各包评分总览

| 包 | 架构 | 抽象 | 依赖 | 实践 | 综合 |
|----|------|------|------|------|------|
| **Kernel** | 8 | 8 | 10 | 9 | **8.8** |
| **Infra** | 7 | 8 | 9 | 9 | **8.3** |
| **Data** | 7 | 7 | 8 | 8 | **7.5** |
| **Analytics** | 8 | 8 | 9 | 9 | **8.5** |
| **Engine** | 10 | 10 | 10 | 9 | **9.8** |
| **App** | 9 | 8 | 10 | 9 | **9.0** |
| **Interfaces** | 9 | 8 | 9 | 8 | **8.5** |
