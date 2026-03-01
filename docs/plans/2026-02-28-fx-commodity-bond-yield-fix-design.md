# FX/Commodity 写入链路及国债收益率异常值修复设计

## 背景

代码审查发现以下问题需要修复：

1. **Critical**: fx_daily / commodity_daily 已暴露入口，但写入链路未实现
2. **High**: 新增 FX/Commodity API 路由不可达，且实现仍是占位返回空列表
3. **High**: 国债收益率适配器会把异常值静默写成 0.0，存在数据污染风险
4. **Medium**: 架构边界被放宽，Port 层开始直接耦合 DataHub sources 实现细节
5. **Medium**: FRED 未配置时，Commodity 走"空数据"分支而不是配置错误分支

## 修复方案

### 第一部分：Critical - 写入链路

#### 1.1 创建 FX Store 层

创建 `packages/datahub/src/ditto_datahub/stores/market/fx/` 目录：
- `bars.py` - FxBarsReader/Writer（参考 IndexBarsReader/Writer 实现）
- `__init__.py`

数据存储路径：`{data_root}/market/fx/bars/{year}.parquet`

#### 1.2 创建 Commodity Store 层

创建 `packages/datahub/src/ditto_datahub/stores/market/commodity/` 目录：
- `bars.py` - CommodityBarsReader/Writer
- `__init__.py`

数据存储路径：`{data_root}/market/commodity/bars/{year}.parquet`

#### 1.3 扩展 MarketService

在 `packages/datahub/src/ditto_datahub/services/market_service.py` 中：
- 添加 `fx_bars_reader/writer` 和 `commodity_bars_reader/writer` 依赖
- 扩展 `save_bars()` 支持 `fx_daily` 和 `commodity_daily`
- 扩展 `find_bars()` 支持 `asset_class="fx"` 和 `asset_class="commodity"`
- 扩展 `InstrumentIdRange` 支持 fx 和 commodity 范围

#### 1.4 扩展 data_writer.py

在 `apps/port/src/ditto_port/services/ingestion/data_writer.py` 中：
- 添加 `Dataset.FX_DAILY` handler → `_write_fx_bars()`
- 添加 `Dataset.COMMODITY_DAILY` handler → `_write_commodity_bars()`

### 第二部分：High - API 路由

#### 2.1 挂载路由

在 `apps/port/src/ditto_port/main.py` 中：
```python
from ditto_port.api.routes import fx, commodity
app.include_router(fx.router, prefix="/api/v1")
app.include_router(commodity.router, prefix="/api/v1")
```

#### 2.2 实现查询逻辑

修改 `apps/port/src/ditto_port/api/routes/fx.py`：
- 注入 MarketService
- 使用 `FX_CODE_TO_INSTRUMENT_ID` 映射获取 instrument_ids
- 调用 MarketService.find_bars() 查询数据
- 转换为 FxBar 模型返回

修改 `apps/port/src/ditto_port/api/routes/commodity.py`：
- 注入 MarketService
- 使用 `COMMODITY_CODE_TO_INSTRUMENT_ID` 和 `VIX_CODE_TO_INSTRUMENT_ID` 映射获取 instrument_ids
- 调用 MarketService.find_bars() 查询数据
- 转换为 CommodityBar 模型返回

### 第三部分：High - 国债收益率异常值

修改 `packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py` 的 `_parse_row` 方法：

```python
# 修改前（错误）
term_float = float(curve_term) if isinstance(curve_term, (int, float)) else 0.0
value_float = float(value) if isinstance(value, (int, float)) else 0.0

# 修改后（正确）
try:
    term_float = float(curve_term)
except (TypeError, ValueError):
    return None  # 跳过异常行

try:
    value_float = float(value)
except (TypeError, ValueError):
    return None  # 跳过异常行
```

同时添加日志记录被跳过的异常数据。

### 第四部分：Medium - FRED 配置错误

修改 `apps/port/src/ditto_port/services/ingestion/factory.py`：
- 在 FRED 未配置时，记录明确的警告日志

修改 `apps/port/src/ditto_port/services/ingestion/coordinator.py`：
- 当 `fred_source is None` 且数据集是 `commodity_daily` 时：
  - 返回**配置错误**状态（如 `status="error"`）
  - 消息说明 "FRED data source not configured"

### 第五部分：测试

- 为 FX/Commodity Store 层添加单元测试
- 添加端到端测试覆盖完整写入链路
- 为国债收益率异常值处理添加测试用例

## 依赖关系

```
1. FX/Commodity Store 层
   ↓
2. MarketService 扩展
   ↓
3. data_writer.py 扩展
   ↓
4. API 路由实现
   ↓
5. 测试
```

## 文件变更清单

### 新增文件
- `packages/datahub/src/ditto_datahub/stores/market/fx/__init__.py`
- `packages/datahub/src/ditto_datahub/stores/market/fx/bars.py`
- `packages/datahub/src/ditto_datahub/stores/market/commodity/__init__.py`
- `packages/datahub/src/ditto_datahub/stores/market/commodity/bars.py`
- `packages/datahub/tests/unit/stores/market/fx/test_bars.py`
- `packages/datahub/tests/unit/stores/market/commodity/test_bars.py`

### 修改文件
- `packages/datahub/src/ditto_datahub/models/common.py` - 扩展 InstrumentIdRange
- `packages/datahub/src/ditto_datahub/services/market_service.py` - 支持 fx/commodity
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py` - 异常值处理
- `apps/port/src/ditto_port/services/ingestion/data_writer.py` - 添加 handlers
- `apps/port/src/ditto_port/services/ingestion/coordinator.py` - FRED 配置错误
- `apps/port/src/ditto_port/api/main.py` - 挂载路由
- `apps/port/src/ditto_port/api/routes/fx.py` - 实现查询
- `apps/port/src/ditto_port/api/routes/commodity.py` - 实现查询

## 风险评估

- **存储格式**：FX/Commodity 使用与 Index 相同的 Parquet 格式，风险低
- **API 兼容**：新增端点，不影响现有端点，风险低
- **数据迁移**：无需迁移，首次运行时创建新文件

## 验收标准

1. `pixi run -e dev check` 全部通过
2. `write_data('fx_daily', ...)` 成功写入数据
3. `write_data('commodity_daily', ...)` 成功写入数据
4. `/api/v1/fx/bars` 返回正确数据
5. `/api/v1/commodity/bars` 返回正确数据
6. 国债收益率异常值不再被静默写成 0.0
7. FRED 未配置时返回明确的错误信息
