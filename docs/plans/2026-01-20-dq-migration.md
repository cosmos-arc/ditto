# DQ 模块重构计划：DataHub → Core 迁移

## 执行摘要

将 DQ（数据质量）模块从 `packages/datahub/dq/` **完整迁移**到 `packages/core/quality/`，严格按照 [architecture.md](d:\\code\\quant\\ditto\\.claude\\rules\\architecture.md) 的分层规范实现：

```
Quality（数据质量）
├── Domain Layer    → packages/core/src/ditto_core/quality/    (纯业务逻辑，零数据访问)
├── Application     → apps/port/services/ingestion/quality/   (编排层，获取数据并注入)
└── Infrastructure  → packages/datahub/accessors/             (数据存储能力)
```

---

## 核心架构原则

**用户明确要求**：
1. **Quality Engine 不存在数据访问层的抽象** - Core 层只有纯业务逻辑
2. **所有数据从编排层注入** - Application Layer 获取数据后传给 Core
3. **DQ 配置遵循项目配置规范** - 在项目根目录按环境组织，支持默认值和覆盖

这意味着：
- **Core Layer**: 纯函数式业务逻辑，零依赖 DataHub
- **Application Layer**: 编排流程，负责从 DataHub 获取数据并注入
- **Infrastructure Layer**: 只提供数据存储能力
- **Configuration**: 按环境分类，支持覆盖机制

---

## DQ 配置设计

### 配置目录结构

遵循项目配置规范，DQ 配置按环境组织：

```
config/
├── development/
│   ├── dq.env                    # DQ 环境变量配置
│   └── dq_rules/                 # 环境特定规则（可选）
│       ├── stock_daily.yml       # 覆盖默认规则
│       └── etf_daily.yml
├── testing/
│   ├── dq.env
│   └── dq_rules/                 # 测试环境规则（可选）
│       └── stock_daily.yml
├── production/
│   ├── dq.env
│   └── dq_rules/                 # 生产环境规则（可选）
│       └── stock_daily.yml
└── default/                      # 新增：默认规则目录
    └── dq_rules/
        ├── stock_daily.yml       # 默认规则
        ├── etf_daily.yml
        ├── index_daily.yml
        ├── adj_factor.yml
        └── index_weight.yml
```

### 配置文件格式

**dq.env** - 环境变量配置：
```bash
# DQ 开关配置
DITTO_DQ_L1_ENABLED=true
DITTO_DQ_L2_ENABLED=true
DITTO_DQ_L3_ENABLED=true

# DQ 规则目录（可覆盖）
# 优先级：环境特定 > 默认
DITTO_DQ_RULES_DIR=config/default/dq_rules

# DQ 隔离区配置
DITTO_DQ_QUARANTINE_ENABLED=true
DITTO_DQ_QUARANTINE_PATH=data/quarantine

# DQ 报告配置
DITTO_DQ_REPORT_ENABLED=true
DITTO_DQ_REPORT_PATH=data/reports/dq
```

### 配置加载优先级

1. **环境特定规则**: `config/{DITTO_ENV}/dq_rules/{dataset}.yml`
2. **默认规则**: `config/default/dq_rules/{dataset}.yml`
3. **包内规则**: `packages/core/config/dq_rules/{dataset}.yml`（后备）

### Settings 类设计

```python
# packages/core/src/ditto_core/quality/config.py

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class DQSettings(BaseSettings):
    """DQ 配置"""

    model_config = SettingsConfigDict(
        env_prefix="DITTO_DQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 开关配置
    l1_enabled: bool = True
    l2_enabled: bool = True
    l3_enabled: bool = True

    # 规则目录
    rules_dir: str = "config/default/dq_rules"

    # 隔离区
    quarantine_enabled: bool = True
    quarantine_path: str = "data/quarantine"

    # 报告
    report_enabled: bool = True
    report_path: str = "data/reports/dq"

    @property
    def rules_path(self) -> Path:
        """获取规则目录路径"""
        # 支持环境变量覆盖
        return Path(self.rules_dir)

    def get_rules_paths(self, dataset: str) -> list[Path]:
        """
        获取规则文件加载路径（优先级从高到低）

        1. 环境特定: config/{env}/dq_rules/{dataset}.yml
        2. 默认: config/default/dq_rules/{dataset}.yml
        3. 包内: packages/core/config/dq_rules/{dataset}.yml
        """
        from ditto_foundation.config import get_settings

        env = get_settings().env
        paths = []

        # 1. 环境特定
        env_rules = Path(f"config/{env}/dq_rules/{dataset}.yml")
        if env_rules.exists():
            paths.append(env_rules)

        # 2. 默认
        default_rules = self.rules_path / f"{dataset}.yml"
        if default_rules.exists():
            paths.append(default_rules)

        # 3. 包内后备
        package_rules = Path(__file__).parent.parent.parent / "config/dq_rules" / f"{dataset}.yml"
        if package_rules.exists():
            paths.append(package_rules)

        return paths
```

### 配置迁移

| 源位置 | 目标位置 |
|--------|----------|
| `packages/datahub/config/dq_rules/*` | `config/default/dq_rules/*` |
| 新建 | `config/development/dq.env` |
| 新建 | `config/testing/dq.env` |
| 新建 | `config/production/dq.env` |

---

## 目标架构

### 新目录结构

```
packages/core/
├── src/ditto_core/
│   └── quality/                     # Domain Layer（纯业务逻辑）
│       ├── __init__.py
│       ├── engine.py                # QualityEngine
│       ├── spec.py                  # 规则配置模型
│       ├── checkers/
│       │   ├── technical.py         # L1 检查（无外部依赖）
│       │   ├── business.py          # L2 检查（无外部依赖）
│       │   └── statistical.py       # L3 检查（数据通过参数传入）
│       └── report.py                # 报告生成器
├── tests/unit/quality/              # 单元测试
└── config/dq_rules/                 # 默认配置文件

apps/port/
├── src/ditto_port/services/ingestion/
│   └── quality/                     # Application Layer（编排逻辑）
│       ├── __init__.py
│       ├── service.py               # QualityService（写入时 DQ 编排）
│       └── l3_batch_service.py      # L3BatchService（批量检查编排）
└── tests/unit/ingestion/quality/    # 应用层测试
```

---

## 依赖解耦设计

### 当前问题

`StatisticalChecker` 直接调用 `hub.bars.get()` 和 `hub.calendar.get()`，违反分层架构。

### 解决方案：数据通过参数注入

**Application Layer 获取数据 → 传给 Core Layer**

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py

class StatisticalChecker:
    """L3 统计异常检查器（纯函数式）"""

    def check_zscore(
        self,
        current: pl.DataFrame,        # 当前数据（传入）
        historical: pl.DataFrame,     # 历史数据（传入）
        column: str,
        window: int,
        threshold: float,
    ) -> DQIssue | None:
        """
        检查 Z-score 异常。

        Args:
            current: 当前数据（由 Application Layer 提供）
            historical: 历史数据（由 Application Layer 从 DataHub 获取）
            column: 检查列
            window: 窗口期
            threshold: 阈值

        Returns:
            DQIssue if anomaly detected, None otherwise
        """
        # 纯函数式计算，无外部依赖
        stats = historical.group_by("sid").agg(
            pl.col(column).mean().alias("mean"),
            pl.col(column).std().alias("std"),
        )
        current = current.join(stats, on="sid")
        anomalies = current.filter(
            ((pl.col(column) - pl.col("mean")) / pl.col("std")).abs() > threshold
        )
        ...
```

```python
# apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py

class L3BatchService:
    """L3 批量检查服务（编排层）"""

    def __init__(
        self,
        engine: QualityEngine,
        hub: DataHub,  # 在这里注入 DataHub
    ) -> None:
        self._engine = engine
        self._hub = hub

    async def check_dataset(
        self,
        dataset: str,
        trade_date: str,
    ) -> DQResult:
        """编排 L3 检查流程"""
        # 1. 从 DataHub 获取历史数据
        historical = self._hub.bars.get(
            start=calculate_start_date(trade_date),
            end=trade_date,
        )

        # 2. 获取当前数据
        current = self._hub.bars.get(
            start=trade_date,
            end=trade_date,
        )

        # 3. 注入数据到 Core Engine
        return self._engine.check_statistical(
            dataset=dataset,
            current=current,      # 注入数据
            historical=historical, # 注入数据
        )
```

---

## 分阶段迁移计划

### Phase 1: 准备阶段（创建目录结构）

```bash
mkdir -p packages/core/src/ditto_core/quality/checkers
mkdir -p packages/core/tests/unit/quality
mkdir -p apps/port/src/ditto_port/services/ingestion/quality
mkdir -p apps/port/tests/unit/ingestion/quality
```

---

### Phase 2: Domain Layer 迁移

#### 2.1 迁移模型定义
**源文件**: `packages/datahub/src/ditto_datahub/models/quality.py`
**目标文件**: `packages/core/src/ditto_core/quality/spec.py`

#### 2.2 迁移 TechnicalChecker
**源文件**: `packages/datahub/src/ditto_datahub/dq/checkers/technical.py`
**目标文件**: `packages/core/src/ditto_core/quality/checkers/technical.py`

#### 2.3 迁移 BusinessChecker
**源文件**: `packages/datahub/src/ditto_datahub/dq/checkers/business.py`
**目标文件**: `packages/core/src/ditto_core/quality/checkers/business.py`

#### 2.4 迁移 StatisticalChecker（核心重构）
**源文件**: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py`
**目标文件**: `packages/core/src/ditto_core/quality/checkers/statistical.py`

**重构内容**：
- 移除 `hub` 参数
- `_check_zscore()`: 改为接收 `current` 和 `historical` DataFrame 参数
- `_check_completeness()`: 改为接收 `calendar` DataFrame 参数
- 纯函数式实现，无外部调用

#### 2.5 迁移 QualityEngine
**源文件**: `packages/datahub/src/ditto_datahub/dq/engine.py`
**目标文件**: `packages/core/src/ditto_core/quality/engine.py`

**重构内容**：
- 重命名类：`DQEngine` → `QualityEngine`
- `check()`: 保持不变（L1/L2 不需要外部数据）
- `check_statistical()`: 接收 `current` 和 `historical` 参数

#### 2.6 创建 DQ Settings
**文件**: `packages/core/src/ditto_core/quality/config.py`

**操作**：
- 创建 `DQSettings` 类（使用 pydantic-settings）
- 支持环境变量配置（`DITTO_DQ_*` 前缀）
- 实现 `get_rules_paths()` 方法（支持覆盖机制）

#### 2.7 迁移配置文件
**源目录**: `packages/datahub/config/dq_rules/`
**目标目录**: `config/default/dq_rules/`

**操作**：
- 复制所有 YAML 配置文件
- 创建环境配置文件：
  - `config/development/dq.env`
  - `config/testing/dq.env`
  - `config/production/dq.env`

---

### Phase 3: Application Layer 编排

#### 3.1 创建 QualityService
**文件**: `apps/port/src/ditto_port/services/ingestion/quality/service.py`

**职责**：
- 编排写入时质量检查（L1 + L2）
- 处理隔离逻辑（调用 QuarantineStore）
- 记录指标和日志

#### 3.2 创建 L3BatchService
**文件**: `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py`

**职责**：
- 从 DataHub 获取历史数据和交易日历
- 注入数据到 QualityEngine
- 发送告警通知

---

### Phase 4: 更新集成点

#### 4.1 更新 DataHubProvider
**文件**: `apps/port/src/ditto_port/registry/datahub.py`

**操作**：
- 导入：`from ditto_core.quality import QualityEngine`
- 修改 `dq_engine` Provider

#### 4.2 更新 BarsAccessor
**文件**: `packages/datahub/src/ditto_datahub/accessors/bars/accessor.py`

**操作**：
- 更新导入：`from ditto_core.quality import QualityEngine`

#### 4.3 更新 L3 批量检查任务
**文件**: `apps/port/src/ditto_port/jobs/tasks/dq_batch.py`

**操作**：
- 使用 `L3BatchService` 替代直接调用

---

### Phase 5: 测试迁移

#### 5.1 迁移 Domain Layer 测试
**源目录**: `packages/datahub/tests/unit/dq/`
**目标目录**: `packages/core/tests/unit/quality/`

#### 5.2 创建 Application Layer 测试
**目录**: `apps/port/tests/unit/ingestion/quality/`

---

### Phase 6: 清理与文档

#### 6.1 移除旧代码
- 删除 `packages/datahub/src/ditto_datahub/dq/`
- 删除 `packages/datahub/tests/unit/dq/`

#### 6.2 向后兼容层
**文件**: `packages/datahub/src/ditto_datahub/models/quality.py`
- 重新导出 Core 的模型

---

## 关键文件路径

### 需要创建的新文件

| 文件 | 说明 |
|------|------|
| `packages/core/src/ditto_core/quality/spec.py` | 规则配置模型 |
| `packages/core/src/ditto_core/quality/config.py` | DQ Settings（环境变量配置） |
| `packages/core/src/ditto_core/quality/engine.py` | QualityEngine |
| `packages/core/src/ditto_core/quality/checkers/technical.py` | L1 检查器 |
| `packages/core/src/ditto_core/quality/checkers/business.py` | L2 检查器 |
| `packages/core/src/ditto_core/quality/checkers/statistical.py` | L3 检查器（纯函数） |
| `config/default/dq_rules/*.yml` | 默认 DQ 规则配置 |
| `config/{env}/dq.env` | 环境特定 DQ 配置 |
| `apps/port/src/ditto_port/services/ingestion/quality/service.py` | QualityService |
| `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py` | L3BatchService |

### 需要修改的现有文件

| 文件 | 修改内容 |
|------|----------|
| `apps/port/src/ditto_port/registry/datahub.py` | 修改 dq_engine Provider |
| `packages/datahub/src/ditto_datahub/accessors/bars/accessor.py` | 更新导入路径 |
| `apps/port/src/ditto_port/jobs/tasks/dq_batch.py` | 使用 L3BatchService |

### 需要迁移的文件

| 源文件 | 目标文件 |
|--------|----------|
| `packages/datahub/src/ditto_datahub/models/quality.py` | `packages/core/src/ditto_core/quality/spec.py` |
| `packages/datahub/src/ditto_datahub/dq/engine.py` | `packages/core/src/ditto_core/quality/engine.py` |
| `packages/datahub/src/ditto_datahub/dq/checkers/technical.py` | `packages/core/src/ditto_core/quality/checkers/technical.py` |
| `packages/datahub/src/ditto_datahub/dq/checkers/business.py` | `packages/core/src/ditto_core/quality/checkers/business.py` |
| `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py` | `packages/core/src/ditto_core/quality/checkers/statistical.py` |
| `packages/datahub/src/ditto_datahub/dq/report.py` | `packages/core/src/ditto_core/quality/report.py` |
| `packages/datahub/config/dq_rules/*` | `config/default/dq_rules/*` |

---

## 验证清单

### 功能完整性
- [ ] 所有 L1/L2/L3 检查功能正常工作
- [ ] 写入时 DQ 检查阻断/警告逻辑正确
- [ ] L3 批量检查任务正常运行
- [ ] 隔离区机制正常工作

### 架构合规性
- [ ] Domain Layer (Core) 零依赖 DataHub
- [ ] 所有数据通过 Application Layer 注入
- [ ] 无数据访问抽象接口
- [ ] 遵循架构依赖规则

### 质量标准
- [ ] 所有测试通过
- [ ] 分支覆盖率 ≥ 80%
- [ ] pyright 类型检查通过
- [ ] ruff 代码检查通过
