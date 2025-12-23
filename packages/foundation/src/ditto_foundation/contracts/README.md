# contracts

> 数据契约定义，使用 Pydantic 和 Pandera 进行类型验证和 Schema 约束

## 一、核心功能

### 1.1 数据验证

- **Pydantic Models**：用于单条记录的结构化验证
- **Pandera Schemas**：用于 DataFrame 的批量数据验证
- **类型安全**：编译时和运行时的双重类型检查
- **约束验证**：字段级别的业务规则验证

### 1.2 契约文件

| 文件 | 框架 | 职责 |
|------|------|------|
| `etf.py` | Pydantic | ETF 信息数据契约 |
| `market_data.py` | Pandera | 市场数据 Schema 定义 |

## 二、架构定位

```
┌─────────────────────────────────────────────────┐
│           数据输入层（外部 API）                  │
└─────────────────┬───────────────────────────────┘
                  │
                  ↓ 契约验证
┌─────────────────────────────────────────────────┐
│        contracts（Pydantic + Pandera）          │
└─────────────────┬───────────────────────────────┘
                  │
                  ↓ 类型安全
┌─────────────────────────────────────────────────┐
│        业务逻辑层（Engine/Service）              │
└─────────────────────────────────────────────────┘
```

- **层级**：基础设施层
- **依赖**：外部库（pydantic、pandera）
- **职责**：定义数据结构和验证规则

## 三、目录结构

```
contracts/
├── __init__.py       # 导出所有 Models 和 Schemas
├── etf.py            # ETF 相关数据契约
└── market_data.py    # 市场数据 Schema
```

## 四、关键模块说明

### 4.1 ETFInfoModel（etf.py）

ETF 信息的 Pydantic 数据模型：

```python
from ditto_foundation.contracts import ETFInfoModel
from datetime import date

etf = ETFInfoModel(
    symbol="510300",
    name="沪深300ETF",
    fund_manager="华夏基金",
    tracking_index="沪深300指数",
    establishment_date=date(2012, 5, 28)
)
```

**字段验证规则**：
- `symbol`：至少 6 个字符，自动转大写
- `name`：至少 2 个字符，自动去除首尾空格
- `establishment_date`：可选的日期类型

### 4.2 DailyPriceSchema（market_data.py）

日线价格数据的 Pandera Schema：

```python
from ditto_foundation.contracts import DailyPriceSchema
import pandera as pa

# 验证 DataFrame
validated_df = DailyPriceSchema.validate(df)
```

**字段验证规则**：
- `symbol`：正则匹配 `^\d{6}\.(SH|SZ)$`
- `trade_date`：正则匹配 `^\d{8}$`（YYYYMMDD）
- 价格字段：必须 >= 0
- `knowledge_date`：PIT 安全的知识日期

**数据检查**：
- `price_consistency`：检查价格一致性
- `high_low_relationship`：检查 high >= max(open, close) 且 low <= min(open, close)

### 4.3 AdjustmentFactorSchema（market_data.py）

复权因子的 Pandera Schema：

```python
from ditto_foundation.contracts import AdjustmentFactorSchema

validated_df = AdjustmentFactorSchema.validate(df)
```

**字段验证规则**：
- `adj_factor`：必须 > 0
- `adj_type`：只能是 "cumulative" 或 "point"

**数据检查**：
- `cumulative_factor_monotonic`：累积复权因子必须单调递增

## 五、注意事项

### 5.1 Pydantic vs Pandera

| 特性 | Pydantic | Pandera |
|------|----------|---------|
| 用途 | 单条记录验证 | DataFrame 批量验证 |
| 输入 | dict/对象 | pandas.DataFrame |
| 位置 | API 边界 | 数据处理管道 |
| 性能 | 快 | 较慢（批量验证）|

### 5.2 PIT 安全

所有市场数据 Schema 必须包含 `knowledge_date` 字段：

```python
knowledge_date: Series[str] = pa.Field(
    str_matches=r"^\d{8}$",
    description="Knowledge date for PIT safety"
)
```

### 5.3 Symbol 格式

ETF 代码格式统一为：`六位代码.交易所`

```python
# 正确格式
"510300.SH"  # 上交所
"159915.SZ"  # 深交所

# 错误格式
"510300"     # 缺少交易所后缀
"sh510300"   # 大小写错误
```

### 5.4 验证失败处理

```python
from pydantic import ValidationError
from pandera.errors import SchemaError, SchemaErrors

# Pydantic 验证失败
try:
    etf = ETFInfoModel(symbol="", name="Invalid")
except ValidationError as e:
    print(e)  # 详细的验证错误信息

# Pandera 验证失败
try:
    validated_df = DailyPriceSchema.validate(invalid_df)
except SchemaErrors as e:
    print(e.failure_cases)  # 查看具体的失败行
```

## 六、使用示例

### 6.1 API 数据验证

```python
from ditto_foundation.contracts import ETFInfoModel
from datetime import date

# 从外部 API 获取的数据
api_data = {
    "symbol": "510300",
    "name": "沪深300ETF",
    "fund_manager": "华夏基金",
    "tracking_index": "沪深300指数",
    "establishment_date": "2012-05-28"
}

# 验证并转换
etf = ETFInfoModel(**api_data)
print(etf.symbol)  # 自动转大写
```

### 6.2 DataFrame 批量验证

```python
from ditto_foundation.contracts import DailyPriceSchema
import pandas as pd

# 构造测试数据
df = pd.DataFrame({
    "symbol": ["510300.SH", "510300.SH"],
    "trade_date": ["20240102", "20240103"],
    "open_price": [4.5, 4.6],
    "high_price": [4.6, 4.7],
    "low_price": [4.4, 4.5],
    "close_price": [4.55, 4.65],
    "volume": [1000000, 1200000],
    "amount": [4550000, 5580000],
    "knowledge_date": ["20240102", "20240103"]
})

# 验证
validated_df = DailyPriceSchema.validate(df)
```

### 6.3 自定义验证规则

```python
from pandera import Field

class CustomSchema(pa.DataFrameModel):
    value: Series[float] = Field(
        ge=0,           # 必须 >= 0
        le=100,         # 必须 <= 100
        in_range={0, 100}  # 在 [0, 100] 范围内
    )

    @pa.check("value")
    @classmethod
    def custom_check(cls, value: Series[float]) -> Series[bool]:
        """自定义验证逻辑."""
        return value > 0  # 必须大于 0
```

### 6.4 可选字段与默认值

```python
from pydantic import BaseModel, Field

class OptionalModel(BaseModel):
    required_field: str
    optional_field: str | None = Field(
        default=None,
        description="可选字段"
    )
```
