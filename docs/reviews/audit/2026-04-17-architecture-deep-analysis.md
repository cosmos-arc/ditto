> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 架构深度分析 — 模块层级、依赖清晰度与抽象恰当性

> **视角**: Clean Architecture + Hexagonal Architecture + DDD + Python 最佳实践
> **日期**: 2026-04-17

---

## 一、模块层级：规范与实际之间的落差

### 1.1 核心问题：规范存在但未被一致执行

项目有一套精心设计的规范体系（CLAUDE.md + 各包 CLAUDE.md + importlinter），但审计发现**规范遵循度在 70-80% 之间**，关键模式（Ports、CQRS、Facade）只在部分域执行。

**Clean Architecture 原则**: 架构规则应该是机器可验证的，而非依赖开发者记忆。

#### 证据 1：Ports 模式 — 定义了但只覆盖 3/8 域

[ports.py](packages/data/src/ditto_data/services/ports.py) 为 Market/Fundamental/Capital 三个域定义了结构化的 `ReadPorts`/`WritePorts`，但：

- `MetadataService` — 接收 **17 个裸参数**（[metadata_service.py](packages/data/src/ditto_data/services/metadata_service.py)）
- `MacroService` — 接收 4 个裸参数
- `TradeService` — 直接注入 `SQLiteClient`
- `ExecutionAuditService` — 直接注入 `SQLitePool`
- 所有 runtime 服务 — 使用不同注入方式

**问题本质**: `Ports` 在项目中充当了两种角色——
1. **Hexagonal Architecture 的 Port**（接口定义，供外部实现）— 这是正确的用法
2. **参数分组 dataclass**（解决 `__init__` 参数过多）— 这是权宜之计

这两个角色混在同一个文件中，导致语义模糊。`MarketReadPorts` 不是 Protocol，它只是一个 `@dataclass` 装着具体类型（`StockBarsReader`、`EtfBarsReader` 等），违反了 **依赖倒置原则（DIP）**——Service 直接依赖了存储层的具体实现类，而非抽象接口。

**业界最佳实践**:
- **Hexagonal Architecture**: Port 应该是 `Protocol` 或 `ABC`，定义在领域层，由基础设施层实现
- **NautilusTrader**: 所有跨组件接口都是 Rust `trait`（等价于 Protocol），从不直接传递具体类

#### 证据 2：CQRS — 在 trade/ 子域完全失效

[trade/intents.py](packages/data/src/ditto_data/services/trade/intents.py:74-119) 中 `TradeIntentWriter` 包含：

```python
class TradeIntentWriter:
    def save(self, record) -> None: ...    # 写
    def get(self, intent_id) -> Record: ... # 读 ← CQRS 违规
    def list(self, ...) -> list[Record]: ... # 读 ← CQRS 违规
    def update_status(self, ...) -> None: ... # 写
```

类名是 "Writer" 但承担了完整 CRUD。FillWriter、PositionWriter 同理。更严重的是，这些 "Writer" 直接包含 DDL（`_CREATE_INTENTS_TABLE`）和 SQL，绕过了 storage 层的 CQRS 架构。

**这不仅是命名问题，而是架构边界被突破**：Service 层直接持有 SQL 语句和表结构定义，storage 层的 Reader/Writer 抽象被架空。

#### 证据 3：Data 层占比 60% — "上帝包"倾向

Data 层 325 文件、46,991 行，占全项目 60%。包含：
- 13 个 Facade Service + 5 个子域服务
- 60+ 个 Reader/Writer
- 3 个数据源适配器
- 完整的质量引擎
- 完整的 DI 体系（11 个 Provider）

**单一职责原则（SRP）**: 一个包不应包含太多不相关的职责。Data 层同时承担了存储、数据源接入、质量检查、衍生数据管理、策略数据管理等职责。这些职责的变化频率和变更原因完全不同。

**对比**: NautilusTrader 将数据分为 `nautilus_data`（纯数据模型）和 `nautilus_network`（数据源接入）和 `nautilus_persistence`（存储），三个独立 crate。

---

## 二、依赖清晰度：方向正确但实现有"漏洞"

### 2.1 importlinter 的"纸老虎"问题

项目自豪地声明 "24 条契约全部通过"，但审计发现其中至少 1 条实质上是**空壳**：

```ini
# .importlinter
[[layers]]
# Data storage must not import data models directly
ignore_imports =
    ditto_data.storage.** -> ditto_data.models
    ditto_data.storage.** -> ditto_data.models.common
    ditto_data.storage.** -> ditto_data.models.storage
    ditto_data.storage.** -> ditto_data.models.metadata
    ditto_data.storage.** -> ditto_data.models.macro
    ditto_data.storage.** -> ditto_data.models.strategy
    ditto_data.storage.** -> ditto_data.models.strategy_run
```

**storage 实际有 57 处 `from ditto_data.models` 导入**，但全部被 `ignore_imports` 豁免。这条规则的存在意义是"提醒开发者注意耦合"，但它不执行任何强制。

**Python 最佳实践**: 如果规则需要大量豁免才能通过，说明规则本身或架构设计需要调整，而非通过 ignore 绕过。正确的做法是：
1. 如果 storage 必须依赖 models（事实如此），则**接受这个耦合**，将其作为设计意图文档化
2. 或者引入 DTO 层解耦（但 DDD 实践表明，如果 Reader/Writer 使用相同的 Record 类型，引入 DTO 是过度设计）

### 2.2 同名异常导致的依赖混乱

```
DataSourceError(Exception)     ← sources/base.py (被 tushare/fred 使用)
DataSourceError(DataError)    ← errors.py (被 app/coordinator 使用)
```

**这是 Python 的经典陷阱**: 同名类在不同模块中定义，`from X import Y` 只取最后注册的那个。当 `coordinator.py` 写 `from ditto_data.errors import SourceFetchError` 时，它拿到的是 `errors.py` 版本，而 source 实际抛出的是 `base.py` 版本。`except SourceFetchError` 静默失败。

**Python 最佳实践**:
- 避免跨模块同名类（PEP 8 没有明确禁止，但实践中是强烈建议）
- 使用 `@final` 或模块级 `__all__` 限制导出
- 异常类应该有唯一的、全局可发现的定义位置

### 2.3 DerivedError 独立继承 — "最小惊讶原则"违反

```python
class DerivedError(Exception):    # 不继承 DataError
class DataError(Exception):       # kernel 定义
```

上层代码写 `except DataError` 期望捕获所有数据层异常，但 `DerivedError` 不在其中。这违反了 **里氏替换原则（LSP）** 和 **最小惊讶原则**。

**对比**: LEAN 将所有异常组织在一个统一的异常层次中；NautilusTrader 的异常也全部继承自基类。

### 2.4 App 层直接读环境变量 — 配置体系断裂

```python
# app/providers.py:140
start = os.environ.get("DITTO_TRADING_CALENDAR_START", "2020-01-01")
```

**十二要素应用（12-Factor App）**: 配置应该从环境中读取，但应该通过统一的配置层（`Settings`/`ConfigProvider`），而非在代码中散落 `os.environ.get()`。

---

## 三、抽象层级：在"过抽象"和"欠抽象"之间摇摆

### 3.1 "过抽象"的案例

#### ports.py 的"伪 Ports"

[ports.py](packages/data/src/ditto_data/services/ports.py) 前面 82 行全部是 import 语句——导入了 30+ 个具体的 Reader/Writer 类。这不是 Port（抽象接口），而是**参数聚合器**。

**正确的 Hexagonal Architecture Port**:
```python
# 应该是 Protocol，而非 dataclass
class MarketReader(Protocol):
    def read_bars(self, query: BarReadQuery) -> pl.DataFrame: ...

class MarketWriter(Protocol):
    def write_bars(self, data: pl.DataFrame, dataset: Dataset) -> WriteResult: ...
```

#### FredSource 继承过宽的 DataSource

`DataSource` 基类定义了 25+ 个抽象方法（股票、ETF、指数、基本面等），但 `FredSource` 只支持宏观数据，约 20 个方法是 `raise NotImplementedError`。

**接口隔离原则（ISP）**: 不应强迫客户端依赖它不使用的方法。`FredSource` 应该只实现 `MacroSource(Protocol)` 或类似的窄接口。

### 3.2 "欠抽象"的案例

#### DataProvider Protocol 只有 4 个方法

[provider.py](packages/data/src/ditto_data/provider.py:76-100):

```python
class DataProvider(Protocol):
    def get_bars(self, query: BarQuery) -> pl.DataFrame: ...
    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame: ...
    def get_schedule(self, start: str, end: str) -> pl.DataFrame: ...
    def get_factor(self, name, instruments, start, end, asof) -> pl.DataFrame: ...
```

Engine 对 Data 的唯一窗口只有 4 个方法。FundamentalService、MacroService、CapitalService、TradeService 完全没有暴露。这意味着：
- App 层的 `BacktestService` 必须直接依赖 Data 层的具体 Service
- Engine 的回测只能使用行情和因子数据，无法使用基本面/资金面数据

**对比**: Zipline 的 `DataPortal` 是统一的读取门面，覆盖所有数据类型。

#### BarQuery 使用字符串而非强类型

```python
instruments: tuple[str, ...]  # "000001.SZ" — 源代码字符串
adj: str = "none"              # 字符串枚举，无类型安全
frequency: str = "daily"      # 同上
```

`adj` 应该是 `Literal["none", "hfq", "qfq"]` 或枚举，`frequency` 同理。`instruments` 使用源代码字符串而非 `InstrumentId`，导致 Engine 和 Data 之间存在隐式的代码→ID 转换层。

### 3.3 Models 层包含行为逻辑

```python
# common.py — Dataset 枚举包含 6 个 @property 方法
class Dataset(StrEnum):
    @property
    def asset_class(self) -> AssetClass | None: ...   # 30 行
    @property
    def date_schedule(self) -> DateScheduleType: ...  # 40 行
    # ...

# InstrumentIdRange.detect_asset_class — ~70 行复杂业务逻辑
```

**DDD 原则**: 枚举是值对象，应该是零行为的。`Dataset.asset_class` 本质上是一个**类型映射表**，应该作为独立的函数或配置，而非枚举方法。

**Python 最佳实践**: `StrEnum` 的 `@property` 在 Python 3.11+ 中技术可行，但语义上违反了枚举的"命名常量集合"语义。如果一个枚举需要 6 个计算属性，它可能应该是一个 `@dataclass(frozen=True)` 而非枚举。

---

## 四、Python 最佳实践差距

### 4.1 类型安全不足

| 位置 | 问题 | Python 最佳实践 |
|------|------|-----------------|
| `BarQuery.adj: str` | 应为 `Literal["none","hfq","qfq"]` | `Literal` 类型提供编译期检查 |
| `BarQuery.frequency: str` | 应为 `Literal["daily","weekly","monthly"]` | 同上 |
| `StrategyRunRecord.status: str` | 应为 `RunStatus` | 枚举字段应用枚举类型 |
| `_SliceView` Protocol `dict[InstrumentId, Any]` | 应为具体类型 | 避免类型逃逸 |
| `AllocationStage.process(context: object)` | 应为 `StrategyContext` | 避免 `object` 类型 |

**Python 3.12+ 最佳实践**: 充分使用 `Literal`、`TypeAlias`、`ParamSpec`、`TypeVar`、`assert_type()` 和 `@overload`。

### 4.2 异常体系设计

当前异常体系有 **3 组同名冲突**、**2 套独立继承树**（DataError vs DataSourceError vs DittoException）、**12 个裸 Exception**。

**Python 最佳实践**:
1. 所有项目异常继承自一个根异常（如 `DittoError`）
2. 每个包最多定义一个异常基类（`DataError`、`EngineError` 等）
3. 异常类不重复定义——唯一定义位置
4. 使用 `__all__` 控制导出，防止同名冲突
5. 考虑使用 `ExceptionGroup`（Python 3.11+）组合多个异常

### 4.3 frozen dataclass 一致性

项目大量使用 `@dataclass(frozen=True)`，这是好的实践。但不一致之处：
- `EngineResult` 使用可变 dataclass
- `StrategyRunRecord.status` 用 `str` 而非 `RunStatus` 枚举
- `Order.created_at` 默认硬编码 `datetime(2026,1,1)`

**Python 最佳实践**: 要么全 frozen 要么不 frozen，混用降低可预测性。

---

## 五、改进建议（按优先级）

### 优先级 1：消除"架构幻觉"（规范与实际不一致）

1. **消除异常同名冲突** — 合并 `sources/base.py` 和 `errors.py` 的异常体系为唯一继承树
2. **让 DerivedError 继承 DataError** — 修复异常捕获遗漏
3. **将 Trade Writer 拆分为 Reader + Writer** — 恢复 CQRS 语义
4. **让 ExecutionAuditService 通过 storage 层** — 消除 Service 层 SQL
5. **更新 importlinter 规则** — 要么删除空壳规则，要么重构使规则可执行

### 优先级 2：修复抽象层级

6. **DataProvider Protocol 扩展** — 至少覆盖 Fundamental/Macro/Capital/Trade 域
7. **BarQuery 强类型化** — `adj`/`frequency` 改为 `Literal` 类型
8. **FredSource 使用窄接口** — 定义 `MacroSource(Protocol)` 替代宽泛的 `DataSource`
9. **Ports 改为 Protocol** — 从参数聚合器升级为真正的抽象接口

### 优先级 3：模块边界调整

10. **考虑 Data 层拆分** — storage/sources/quality 可以独立为子包或独立包
11. **Kernel 准入标准执行** — 移出 RiskScope/MacroCategory/MacroFrequency 和临时类型
12. **Infra 层清除领域知识** — data_root.py/config_validation.py/checksum.py 的业务逻辑移至 Data 层

### 优先级 4：Python 最佳实践对齐

13. **统一异常根类** — `DittoError(Exception)` 作为所有项目异常的根
14. **消除裸 Exception 继承** — 12 个裸 Exception 归入对应包的异常基类
15. **Models 层零行为** — Dataset 枚举的 `@property` 迁移为独立函数
16. **类型安全加固** — 消除 `Any`/`object` 类型，使用 `Literal`/枚举
