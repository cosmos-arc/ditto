# 摄入层重构设计（2026-03-03）

## 背景

基于 2026-03-03 架构审计报告，ARCH-001 指出 `IngestionCoordinator` 职责过重（968 行），需要拆分。

## 决策记录

### D1: 跳过 MetadataService 拆分（ARCH-002）

**原因**：
- 项目处于开发阶段，没有权限控制、缓存分层的实际需求
- 拆分增加 4 个文件，增加心智负担
- YAGNI 原则，等真正需要时再拆

### D2: 跳过 Ports 接口化（ARCH-003）

**原因**：
- 项目只有一个 Store 实现（SQLite），不打算换实现
- Protocol 在运行时零收益，只是静态类型更"纯粹"
- 34 个导入确实多，但改动频率低

### D3: 事务抽象层需要实现（ENG-001）

**目标**：统一 22 个 Writer 的事务/日志/指标处理

**方案**：
- 新增 `packages/datahub/src/ditto_datahub/stores/base/transactional.py`
- 提供 `transaction_scope` 上下文管理器
- 22 个 Writer 一次性替换，无需兼容层

### D4: 输入规范化需要实现（ENG-003）

**目标**：移除 `golden.py` 中的 4 处 `# type: ignore`

**方案**：
- 引入两阶段解析模型：`RawTickerItem` + `NormalizedTicker`
- 使用 `TypeAdapter` 先解析再规范化

### D5: Ingestion 架构采用插件模式

**核心理念**：
- 每个 dataset 定义自己的 Ingestion handler（fetch + transform + write）
- Coordinator 只是调度器，基于注册的 handler 执行
- 新增 dataset 只需新增一个 Ingestion 实现并注册

**不是**：
- ~~写入能力下沉到 DataHub Service~~
- ~~获取能力下沉到 DataHub Source~~
- ~~自动补偿机制~~

### D6: 自动补偿改为反馈机制

**决策**：
- 不做自动补偿（如 `_auto_init_stock_instrument`）
- 基础数据（stock_basic/etf_basic/index_basic）应率先建立映射
- 在 `IngestionResult` 中返回 `missing_instruments`，供调用方处理

## 设计概要

### 核心抽象

```python
class Ingestion(ABC):
    """摄入策略抽象"""

    @property
    @abstractmethod
    def dataset(self) -> str: ...

    @abstractmethod
    def fetch(self, ctx: IngestionContext, trade_date: str, params: dict | None) -> pl.DataFrame: ...

    @abstractmethod
    def transform(self, ctx: IngestionContext, df: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]: ...

    @abstractmethod
    def write(self, ctx: IngestionContext, df: pl.DataFrame, trade_date: str) -> int: ...

    def execute(self, ctx: IngestionContext, trade_date: str, params: dict | None) -> IngestionResult:
        """模板方法：fetch → transform → write"""
        ...
```

### Coordinator 职责

- 注册所有 Ingestion handler
- 检查增量（是否已摄入）
- 调度执行
- 记录摄入日志
- 返回结果（包含缺失标的信息）

### 预期目录结构

```
apps/port/src/ditto_port/services/ingestion/
├── __init__.py
├── base.py              # Ingestion 抽象基类
├── context.py           # IngestionContext
├── result.py            # IngestionResult
├── coordinator.py       # 调度器（精简版）
├── metadata.py          # MetadataManager（已存在）
├── datasets/            # 各 dataset 的 Ingestion 实现
│   ├── __init__.py
│   ├── stock_daily.py
│   ├── etf_daily.py
│   ├── balance_sheet.py
│   └── ...
└── registry.py          # Ingestion 注册
```

## 待详细设计

- [ ] Ingestion 接口的最终形态
- [ ] IngestionContext 包含哪些依赖
- [ ] IngestionResult 的完整字段
- [ ] transform 返回 `tuple[DataFrame, list[str]]` 是否优雅
- [ ] Registry 如何注册和发现 Ingestion
- [ ] 缺失标的的反馈和处理流程
- [ ] 按标的摄取（ingest_by_instrument）如何适配
- [ ] 与现有 DataHub Service 的交互边界

## 修改计划

### Phase 1: 基础设施（Week 1）
- [ ] PR-1: 事务抽象层（ENG-001）
- [ ] PR-2: 输入规范化（ENG-003）

### Phase 2: 摄入层重构（Week 2-3）
- [ ] PR-3: Ingestion 插件架构实现
- [ ] PR-4: Coordinator 精简
- [ ] PR-5: 各 dataset Ingestion 迁移

### Phase 3: 收尾优化（Week 4）
- [ ] PR-6: 配置覆盖解析器（ENG-002）
- [ ] PR-7: async/sync 纠正（ENG-004）
- [ ] PR-8: Provider 样板提炼（ENG-005）
- [ ] PR-9: legacy 开关治理（ENG-006）

---

*文档创建于 2026-03-03，状态：设计中*
