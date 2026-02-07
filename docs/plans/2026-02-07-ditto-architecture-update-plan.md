# 文档修改计划

## 概述

移除 Contract 层，所有共享模型定义在 DataHub 层，Core 仅依赖 DataHub 的模型定义。

## 需要修改的位置

### 1. 架构图 (1.2)

移除 Contracts Layer，调整 Core 层描述：
```
Core Layer: 业务逻辑层（仅依赖 DataHub 模型）
    ↓ 使用 DataHub 的模型（dataclass/Schema）
```

DataHub Layer 增加 Models 部分：
```
DataHub Layer: 数据访问层（模型 + 实现）
    - Models (共享模型定义)
        - Schema: BAR_SCHEMA, QUOTE_SCHEMA
        - 模型: Order, Position, Portfolio
```

### 2. 核心原则 (1.3/1.4)

删除 "Contract 为中心"，替换为：
- **模型集中**：所有共享模型定义在 DataHub 层
- **Core 依赖限制**：Core 仅依赖 DataHub 的模型定义，不依赖 Service/Store

### 3. 数据模型使用规范

| 类型 | 位置 | 说明 |
|------|------|------|
| API 模型 | Port 层 | Pydantic 请求/响应，仅 API 使用 |
| 共享模型 | DataHub 层 | 所有跨层共享的数据契约 |

### 4. 依赖规则 (新增 1.5)

| 层级 | 可依赖 | 禁止依赖 | 说明 |
|------|--------|----------|------|
| Port | DataHub (Service)、DataHub (模型) | - | 可使用 DataHub 的所有内容 |
| Core | **DataHub (模型定义)** | DataHub (Service/Store) | 仅使用模型，不使用实现类 |
| DataHub | Foundation | Port/Core | 基础设施层 |

**示例**：
```python
# ✅ Core 可以使用 DataHub 的模型
from ditto_datahub.models import Order, Position, Portfolio

# ❌ Core 不能使用 DataHub 的 Service/Store
from ditto_datahub.services import MarketService  # 禁止
from ditto_datahub.stores import BarsStore  # 禁止
```

### 5. 目录结构

移除 `packages/contracts/`，在 DataHub 下增加 `models/`：

```
DataHub/
├── models/              # 新增：所有共享模型定义
│   ├── market/          # Schema 定义
│   │   ├── bar.py       # BAR_SCHEMA
│   │   └── quote.py
│   ├── trading/         # 业务模型
│   │   ├── order.py     # Order (dataclass)
│   │   ├── trade.py
│   │   └── position.py
│   ├── portfolio/
│   │   ├── portfolio.py
│   │   └── account.py
│   └── strategy/
│       ├── signal.py
│       └── state.py
│
├── services/
├── stores/
└── sources/
```

### 6. 删除第十二章

原 "Contracts 层设计" 章节完全删除或重写为 "DataHub 模型层"

### 7. 更新第十三章目录结构

移除 contracts/ 包的描述

### 8. 其他章节

- 删除所有 "Contracts Layer" 的引用
- 更新依赖关系说明

## 修改后版本：5.13
