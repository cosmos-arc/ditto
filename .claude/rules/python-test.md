---
paths: tests/**/*.py
---

# 测试规范

## 测试组件栈

**必须使用以下组件，不得替换**：

| 组件 | 用途 | 使用场景 |
|------|------|----------|
| `pytest` | 测试框架 | 所有测试 |
| `polars.testing` | DataFrame断言 | 数据处理验证 |
| `polars.testing.parametric` | DataFrame生成 | Property测试 |
| `pandera[polars]` | Schema验证 | 数据合同、运行时检查 |
| `hypothesis` | Property-based测试 | 边界条件、数值计算 |
| `pytest-mock` | Mock框架 | 需要验证调用的场景 |
| `monkeypatch` | 简单替换 | 环境变量、属性替换 |
| `respx` | HTTP Mock | 外部API测试 |
| `inline-snapshot` | 快照测试 | 回测结果、API响应 |
| `pytest-cov` | 覆盖率 | CI集成 |

## 目录结构

```
tests/
├── conftest.py
├── fixtures/
├── unit/           # 80% - 每次提交，完全 Mock，测原子功能
└── integration/    # 20% - CI运行，测"接缝"处（DAO、HTTP Client）
```

**测试分类原则**：
- **单元测试**：完全 Mock，测试单个类的自身逻辑
- **集成测试**：真实组件，测试系统与外部的"接缝"处（DAO 写入数据库、HTTP Client 解析 API 响应）

### 🔴 强制要求：测试目录必须镜像源码目录结构

**核心原则**：测试目录结构必须与源码目录结构保持一致，任何源码目录重构必须同步更新测试目录。

#### 目录映射规则

```
src/ditto_foundation/                    tests/unit/
├── cache/                    →          ├── cache/
├── checksum/                 →          ├── checksum/
├── config/                   →          ├── config/
├── db/                       →          ├── db/
└── observability/            →          └── observability/

src/ditto_datahub/                       tests/unit/
├── alerts/                   →          ├── alerts/
├── accessors/                →          ├── accessors/
├── stores/                   →          ├── stores/
├── dq/                       →          ├── dq/
├── models/                   →          ├── models/
└── runtime/                  →          └── runtime/

src/ditto_port/                           tests/unit/
├── cli/                      →          ├── cli/
├── services/                 →          ├── services/
├── jobs/                     →          ├── jobs/
├── models/                   →          ├── models/
└── registry/                 →          └── registry/
```

#### 源码重构时的测试目录更新检查清单

**任何涉及以下操作的重构，必须同步更新测试目录**：

- [ ] 创建新源码目录 → 创建对应的测试目录
- [ ] 删除源码目录 → 删除对应的测试目录
- [ ] 重命名源码目录 → 重命名对应的测试目录
- [ ] 移动源码文件 → 移动对应的测试文件
- [ ] 合并源码目录 → 合并对应的测试目录

#### 禁止的目录结构模式

| ❌ 禁止模式 | ✅ 正确模式 | 原因 |
|-----------|-----------|------|
| 测试文件散布在根目录 | 按源码模块分组 | 难以维护 |
| `utils/` 测试目录（源码无 utils） | 对应具体源码模块 | 镜像原则 |
| `test_observability_unit.py` 重复 | 使用唯一命名或子目录 | 避免 import 冲突 |
| `ingestion/` 测试（源码是 `services/ingestion/`） | `services/ingestion/` | 保持一致 |

#### 检测命令

**重构后必须运行**：

```bash
# 1. 检查测试收集是否正常（无 import 冲突）
pixi run -e dev pytest --collect-only -q 2>&1 | grep -i "error\|mismatch"

# 2. 验证目录结构一致性
# 对比源码和测试目录结构
python -c "
import os
from pathlib import Path

def get_dirs(path):
    return {d.name for d in Path(path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}

src_dirs = get_dirs('packages/foundation/src')
test_dirs = get_dirs('packages/foundation/tests/unit')

missing = src_dirs - test_dirs
extra = test_dirs - src_dirs

if missing:
    print(f'❌ 缺失测试目录: {missing}')
if extra:
    print(f'⚠️  多余测试目录: {extra}')
if not missing and not extra:
    print('✅ 目录结构一致')
"
```

#### 示例：正确的重构流程

```bash
# 场景：重命名源码目录 cache/ → caching/

# 1. 重命名源码目录
git mv src/ditto_foundation/cache/ src/ditto_foundation/caching/

# 2. 同步重命名测试目录（强制要求）
git mv tests/unit/cache/ tests/unit/caching/

# 3. 更新导入语句
# （IDE 会自动处理）

# 4. 验证测试收集
pixi run -e dev pytest --collect-only -q

# 5. 运行测试验证
pixi run -e dev pytest tests/unit/caching/

# 6. 提交变更（源码 + 测试一起提交）
git commit -m "refactor: rename cache to caching

- 重命名源码目录 cache/ → caching/
- 同步更新测试目录结构
- 更新相关导入语句"
```

---

## 单元测试 vs 集成测试边界

### 核心判断标准：**是否测试系统与外部的"接缝"处**

**关键原则**：
- **单元测试**：完全 Mock，测试单个类的原子功能
- **集成测试**：真实组件，测试"接缝"处的契约和配置

| 测试维度 | 单元测试 ✅ | 集成测试 ✅ | 判断依据 |
|---------|-----------|-------------|----------|
| **测试目标** | 单个类的原子功能 | 系统/外部的"接缝"处 | 类自身逻辑 vs 接口契约 |
| **依赖策略** | **完全 Mock** | **真实组件** | 隔离逻辑 vs 验证连接 |
| **数据持久化** | 不关心 | 关键（验证写入/读取） | DAO 写入数据库 |
| **外部调用** | Mock HTTP 调用 | 真实 Client + Mock 响应 | API 响应解析 |
| **典型场景** | 算法逻辑、状态机、数据转换 | DAO、HTTP Client、消息队列 | 内部逻辑 vs 外部接口 |
| **速度** | 快（毫秒级） | 慢（秒级，有真实 IO） | 无 IO vs 有 IO |
| **资源隔离** | Mock（无状态） | `:memory:` / `tmp_path` | 临时资源，与真实数据隔离 |

### 单元测试：完全 Mock，测原子功能

```python
# ✅ 单元测试：所有依赖都是 Mock

def test_datahub_is_trading_day_delegates_correctly(mocker):
    """测试 DataHub 委托逻辑，不关心 Calendar 如何实现"""
    # Mock 所有依赖
    mock_calendar = mocker.Mock()
    mock_calendar.is_trading_day.return_value = True

    # 直接创建被测对象
    hub = DataHub(
        data_root=Path("/tmp"),
        calendar=mock_calendar,
        # ... 其他 Mock 依赖
    )

    # 验证委托逻辑
    result = hub.is_trading_day("2024-01-02")
    mock_calendar.is_trading_day.assert_called_once_with("2024-01-02")
    assert result is True
```

**单元测试特征**：
- ✅ 快速（毫秒级）
- ✅ 可并行（完全隔离）
- ✅ 无外部依赖
- ✅ 每次提交运行
- ✅ 聚焦单个类的逻辑正确性

### 集成测试：真实组件，测"接缝"处

```python
# ✅ 集成测试：测试 DAO 与数据库的"接缝"

@pytest.mark.integration
def test_security_store_can_write_and_read_sqlite():
    """测试 SecurityStore 能否正确写入 SQLite 数据库"""
    # 真实 SQLite 数据库（:memory:，与真实数据隔离）
    pool = SQLitePool(":memory:", schema_path=_SCHEMA_PATH)
    pool.init_schema()

    # 真实 SecurityStore
    sqlite_client = SQLiteClient(pool)
    store = SecurityStore(sqlite_client)

    # 验证"接缝"：能否写入数据库
    store.add_security(sid=1000001, symbol="000001.SZ", source="tushare")

    # 验证"接缝"：能否读取数据库
    df = store.get_by_sid(1000001)
    assert df["symbol"][0] == "000001.SZ"
```

```python
# ✅ 集成测试：测试 HTTP Client 与外部 API 的"接缝"

@pytest.mark.integration
def test_tushare_client_can_parse_api_response(respx_mock):
    """测试 TushareClient 能否正确解析 API 响应"""
    # Mock HTTP 响应（验证解析逻辑，不是测试网络）
    respx_mock.get("https://api.tushare.pro").mock(
        return_value=httpx.Response(200, json={
            "data": {"items": [["2024-01-02", True]]}
        })
    )

    # 真实 HTTP Client（测试解析响应的能力）
    client = TushareClient(token="test")
    df = client.fetch_calendar("2024-01-01", "2024-01-05")

    # 验证"接缝"：能否解析 API 响应格式
    assert len(df) == 1
    assert df["trade_date"][0] == "2024-01-02"
```

**集成测试特征**：
- ⚠️ 较慢（秒级，有真实 IO）
- ✅ 使用临时资源（`:memory:`、`tmp_path`，与真实数据隔离）
- ✅ 真实组件（验证契约和配置）
- ✅ 只测连接点，不测逻辑
- ✅ 关注"组件 A 传给组件 B 的数据，B 能不能认"

**资源隔离策略**：
- **SQLite**：使用 `:memory:`（内存数据库）
- **文件**：使用 `tmp_path`（临时目录）
- **HTTP**：使用 `respx.mock()`（Mock 响应，真实 Client）

### 测试分类决策树

```
开始
  ↓
测试目标是什么？
  ├─ 单个类的逻辑功能 → 单元测试 ✅（完全 Mock）
  └─ 系统/外部的接口 → 集成测试 ✅（真实组件）
      ↓
      接缝类型是什么？
      ├─ DAO/数据库 → 集成测试（验证写入/读取）
      ├─ HTTP Client/API → 集成测试（验证响应解析）
      └─ 消息队列/缓存 → 集成测试（验证序列化/网络）
```

### 关键区别：Mock vs 真实组件

| 场景 | 单元测试（Mock） | 集成测试（真实） |
|------|-----------------|----------------|
| **DAO** | `mocker.Mock()` | 真实数据库 + 真实 SQL |
| **HTTP Client** | `respx.mock()` | 真实 Client + Mock 响应 |
| **DataHub** | Mock 所有 Accessor | （不测，中间层无接缝） |

### 常见误区

#### ❌ 误区：测试多个组件协作 = 集成测试

```python
# ❌ 错误理解：使用了多个组件 = 集成测试
# ✅ 正确理解：只要所有依赖都是 Mock = 单元测试

def test_facade_delegates_correctly(mocker):
    """测试 Facade 的委托逻辑"""
    # Mock 所有依赖（完全隔离）
    mock_dep1 = mocker.Mock()
    mock_dep2 = mocker.Mock()

    facade = Facade(dep1, dep2)
    facade.do_something()

    # 验证委托逻辑（单元测试）
    mock_dep1.method1.assert_called_once()
    mock_dep2.method2.assert_called_once()
```

**关键判断**：
- ✅ Mock 所有依赖 → 单元测试（测试委托逻辑）
- ❌ 真实组件（如 DAO）→ 集成测试（测试接缝）

### 参考资源

- [Using DI container in unit tests - StackOverflow](https://stackoverflow.com/questions/32594803/using-di-container-in-unit-tests)
- [How not to do DI: configuring the IoC container in unit test projects - DevTrends](https://www.devtrends.co.uk/blog/how-not-to-do-dependency-injection-configuring-the-ioc-container-in-unit-test-projects)

### CLI 集成测试边界

**核心原则**：CLI 集成测试只测试 CLI 命令调用了正确的内部函数，不测试函数执行结果。

| 测试维度 | CLI 集成测试 ✅ | CLI 单元测试 ✅ |
|---------|---------------|----------------|
| **测试目标** | CLI 命令触发正确的内部函数 | CLI 参数解析、验证逻辑 |
| **验证内容** | 函数是否被调用，参数是否正确 | 参数验证、错误处理 |
| **依赖策略** | Mock 内部函数 | Mock 所有依赖 |
| **函数结果** | ❌ 不验证（由单元测试保证） | ❌ 不验证 |

```python
# ✅ 正确：CLI 集成测试（测试函数调用）

@pytest.mark.integration
def test_cli_stock_daily_calls_ingest_function(mocker, tmp_path: Path):
    """测试 CLI 命令调用了正确的摄入函数"""
    # Mock 内部函数（验证调用，不关心结果）
    mock_ingest = mocker.patch("ditto_port.cli.ingest.ingest_stock_daily")

    # 执行 CLI 命令
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02"],
    )

    # 验证：命令成功 + 函数被调用
    assert result.exit_code == 0
    mock_ingest.assert_called_once_with(symbol="000001.SZ", date="2024-01-02")
```

```python
# ✅ 正确：CLI 单元测试（测试参数验证）

@pytest.mark.unit
def test_cli_validates_date_format():
    """测试 CLI 日期格式验证逻辑"""
    # 测试无效日期格式
    result = runner.invoke(app, ["stock", "daily", "2024/01/02"])
    assert result.exit_code == 1
    assert "日期格式" in result.stdout or "format" in result.stdout
```

```python
# ❌ 错误：CLI 集成测试测试函数执行结果

@pytest.mark.integration
def test_cli_stock_daily_result(mocker, tmp_path: Path):
    """错误：测试函数执行结果（应该是单元测试）"""
    mock_ingest = mocker.patch("ditto_port.cli.ingest.ingest_stock_daily")
    mock_ingest.return_value = 100  # ← 不要在集成测试中验证返回值

    result = runner.invoke(app, ["stock", "daily", "2024-01-02"])

    assert result.exit_code == 0
    assert mock_ingest.return_value == 100  # ❌ 不应该在这里验证
```

**关键区别**：
- ✅ CLI 集成测试：验证"CLI 命令 → 内部函数"的连接（接缝）
- ✅ CLI 单元测试：验证参数解析、验证逻辑
- ✅ 函数单元测试：验证函数执行结果
- ❌ CLI 集成测试：不验证函数执行结果（由函数单元测试保证）

**边界判断**：
```
CLI 集成测试关注点：
├─ 命令是否触发正确的函数？
├─ 参数是否正确传递？
└─ 错误处理是否正确？

不关注：
├─ 函数执行结果（由函数单元测试保证）
├─ 数据库写入成功（由 DAO 集成测试保证）
└─ 外部 API 调用（由 Client 集成测试保证）
```

### 🔴 强制要求：文件命名规范（防止 import 冲突）

**绝对禁止同名测试文件存在于不同测试层级**：

```
# ❌ 错误：会导致 pytest 收集冲突
packages/datahub/tests/unit/stores/test_pipeline_store.py
packages/datahub/tests/integration/stores/test_pipeline_store.py

# ❌ 错误：跨包同名也会冲突
packages/foundation/tests/unit/observability/test_observability_unit.py
packages/datahub/tests/unit/stores/test_observability_unit.py

# ✅ 正确：添加层级后缀区分
packages/datahub/tests/unit/stores/test_pipeline_store_unit.py
packages/datahub/tests/integration/stores/test_pipeline_store_integration.py

# ✅ 正确：添加模块前缀避免跨包冲突
packages/foundation/tests/unit/observability/test_observability_unit.py
packages/datahub/tests/unit/stores/test_stores_observability_unit.py
```

#### 命名规则

| 测试类型 | 文件命名格式 | 示例 |
|---------|-------------|------|
| 单元测试 | `test_{module}_unit.py` | `test_bars_accessor_unit.py` |
| 集成测试 | `test_{module}_integration.py` | `test_bars_store_integration.py` |

#### 特殊命名场景

| 场景 | 命名策略 | 示例 |
|------|---------|------|
| 跨包可能冲突 | 添加包/模块前缀 | `test_stores_observability_unit.py` |
| 测试多个类 | 使用主要类名 | `test_backfill_manager_unit.py` |
| 测试配置类 | 添加 `_config` 后缀 | `test_ingestion_config_unit.py` |
| 特定功能测试 | 添加功能前缀 | `test_sql_engine_injection_unit.py` |

#### 检测命令

**提交前必须运行**：

```bash
# 1. 检查 import 冲突
pixi run -e dev pytest --collect-only -q 2>&1 | grep -i "import mismatch"

# 2. 检查同名文件
python -c "
from collections import defaultdict
from pathlib import Path

test_files = defaultdict(list)
for py_file in Path('.').rglob('tests/**/test_*.py'):
    name = py_file.name
    test_files[name].append(py_file)

for name, files in test_files.items():
    if len(files) > 1:
        print(f'❌ 同名文件冲突: {name}')
        for f in files:
            print(f'   - {f}')
"

# 3. 验证命名规范
python -c "
from pathlib import Path
import re

unit_tests = list(Path('.').rglob('tests/unit/**/test_*_unit.py'))
integration_tests = list(Path('.').rglob('tests/integration/**/test_*_integration.py'))

print(f'✅ 单元测试: {len(unit_tests)} 个')
print(f'✅ 集成测试: {len(integration_tests)} 个')

# 检查命名不符合规范的
for test_file in Path('.').rglob('tests/**/test_*.py'):
    name = test_file.name
    if 'unit' in str(test_file):
        if not name.endswith('_unit.py'):
            print(f'⚠️  单元测试命名不规范: {test_file}')
    elif 'integration' in str(test_file):
        if not name.endswith('_integration.py'):
            print(f'⚠️  集成测试命名不规范: {test_file}')
"
```

---

## 编写规则

### 命名

```python
# ✅ test_calculate_sharpe_ratio_returns_zero_when_std_is_zero
# ❌ test_sharpe
```

### AAA模式

```python
def test_xxx():
    # Arrange - 准备数据
    # Act - 执行代码
    # Assert - 验证结果
```

### 单一职责

每个测试只验证一个行为，不要在一个测试中验证多个场景。

### 禁止假测试（绝对禁止）

| 形式 | 状态 | 原因 |
|------|------|------|
| `assert True` | ❌ | 没有实际验证 |
| `assert False` | ❌ | 永远失败 |
| 空的 `pass` | ❌ | 无断言 |
| `assert result is not None` | ❌ | 过于宽泛 |

```python
# ✅ 正确：验证具体行为
assert result.status == "success"
assert result.count == 3

# ✅ 测试异常路径
with pytest.raises(ValueError, match="Invalid input"):
    function_with_invalid_input()
```

**检查命令**：
```bash
grep -r "assert True" tests/
grep -r "assert False" tests/
```

---

## DataFrame测试

```python
from polars.testing import assert_frame_equal
assert_frame_equal(result, expected, atol=1e-4)
```

### Property测试

```python
from polars.testing.parametric import dataframes, column
from hypothesis import given

@given(dataframes(cols=[column("price", dtype=pl.Float64)], min_size=10))
def test_calculation_properties(df: pl.DataFrame):
    ...
```

### Schema验证

```python
import pandera.polars as pa

class QuoteSchema(pa.DataFrameModel):
    date: pl.Date
    symbol: str
    price: float = pa.Field(gt=0)

QuoteSchema.validate(df)
```

---

## Mock选择

| 场景 | 工具 |
|------|------|
| 验证调用参数/次数 | `pytest-mock (mocker)` |
| 简单替换返回值 | `monkeypatch.setattr()` |
| 环境变量 | `monkeypatch.setenv()` |
| HTTP请求 | `respx` |

```python
# ✅ 推荐
def test_api(mocker):
    mock_get = mocker.patch("httpx.Client.get")
    mock_get.return_value = httpx.Response(200, json={"price": 15.5})
    result = fetch_quote("000001")
    mock_get.assert_called_once_with("https://api.example.com/quote?symbol=000001")

# ❌ 禁止：unittest.mock
from unittest.mock import patch  # 不要使用
```

---

## 测试类型

### PIT (Point-in-Time) 测试

量化系统核心测试，验证无未来数据泄露。

```python
@pytest.mark.pit
def test_no_future_data_in_features(sample_quotes):
    features = calculate_features(sample_quotes, as_of=date(2024, 1, 15))
    assert features["date"].max() <= date(2024, 1, 15)

@pytest.mark.pit
def test_signal_uses_only_past_data():
    signal_date = date(2024, 1, 15)
    signals = generate_signals(as_of=signal_date)
    for signal in signals:
        assert signal.data_date < signal_date
```

### 可观测性测试

**核心原则**：测试你的代码是否正确"发射"了数据，不测试外部服务本身

**最佳实践**：
- ✅ 使用 In-Memory Registry（Prometheus `CollectorRegistry`）
- ✅ 验证关键指标的发射
- ❌ 不测试 VictoriaMetrics 服务
- ❌ 不过度测试（每个日志点都测）

```python
# ✅ 正确：使用 In-Memory Registry 测试指标发射

from prometheus_client import CollectorRegistry, Counter

@pytest.mark.integration
def test_metrics_increment_correctly():
    """测试代码正确发射了计数指标"""
    # 使用内存 Registry（与真实数据隔离）
    registry = CollectorRegistry()

    # 创建被测组件，注入测试 Registry
    counter = Counter("api_requests_total", "Total API requests", registry=registry)
    counter.labels(method="GET", endpoint="/api/quote").inc()

    # 验证指标已发射
    metric_value = registry.get_sample_value("api_requests_total", {
        "method": "GET",
        "endpoint": "/api/quote"
    })

    assert metric_value == 1.0
```

```python
# ✅ 正确：测试关键业务指标

@pytest.mark.integration
def test_data_ingestion_metrics():
    """测试数据摄入关键指标"""
    registry = CollectorRegistry()

    # 执行业务操作
    ingest_data(symbol="000001.SZ", date="2024-01-02", registry=registry)

    # 验证关键指标（不是每个日志点）
    assert registry.get_sample_value("ingestion_records_total", {
        "status": "success"
    }) == 100.0

    assert registry.get_sample_value("ingestion_duration_seconds", {
        "source": "tushare"
    }) > 0
```

```python
# ❌ 错误：测试外部服务（不要这样做）

@pytest.mark.integration
def test_victoriametrics_saves_metrics():
    """错误：测试 VictoriaMetrics 服务本身"""
    response = requests.get("http://localhost:8428/api/v1/query?query=up")
    assert response.status_code == 200  # 这是测试服务，不是你的代码
```

**测试覆盖策略**：
- **关键指标**：必须测试（如摄入成功率、API 调用计数）
- **诊断指标**：可选测试（如处理耗时、队列大小）
- **调试日志**：不测试（日志太多，成本高）

### 快照测试

**使用规则**：输出结构复杂（>3个字段）且需要防止意外变更时用快照；简单断言（≤3个字段）或含随机/时间值时不用。

| 场景 | 适用 |
|------|------|
| 回测报告 | ✅ 多字段摘要 |
| 信号输出 | ✅ 策略信号列表 |
| 简单断言 | ❌ 用 `assert` 更清晰 |
| 含随机/时间值 | ❌ 每次都变 |

```python
from inline_snapshot import snapshot

def test_backtest_output():
    result = run_backtest(...)
    assert result.summary == snapshot({
        "total_return": 0.156,
        "sharpe_ratio": 1.23,
    })
```

### 异步测试

```python
@pytest.mark.asyncio
async def test_async_data_fetch():
    result = await fetch_data_async("000001")
    assert result is not None

# 异步 + 参数化
@pytest.mark.asyncio
@pytest.mark.parametrize("symbol,expected_sid", [
    ("000001", 1000001),
    ("000002", 1000002),
])
async def test_resolve_sid_async(symbol, expected_sid):
    sid = await async_resolve_sid(symbol)
    assert sid == expected_sid
```

### 参数化测试（减少重复）

**当测试逻辑相同，只是输入/输出不同时，必须使用参数化测试**：

```python
# ❌ 错误：重复代码
def test_read_filter_by_sids_1(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000001])
    assert len(df) == 3

# ✅ 正确：参数化测试
@pytest.mark.parametrize("sids,expected_count", [
    ([1000001], 3),           # 单个 SID
    ([1000002], 1),           # 另一个 SID
    ([1000001, 1000002], 4),  # 多个 SID
    ([], 0),                  # 空 SID 列表
])
def test_read_filter_by_sids(self, store, sample_df, sids, expected_count):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=sids)
    assert len(df) == expected_count
```

---

## Parquet Store 测试

```python
@pytest.fixture
def store(tmp_path):
    """临时目录的ParquetStore"""
    return QuoteParquetStore(base_path=tmp_path / "quotes")

def test_partitioned_write(store, sample_quotes):
    store.save(sample_quotes, partition_by="symbol")
    assert (store.base_path / "symbol=000001").exists()
```

**不需要测**：Parquet格式正确性（那是Polars的责任）

---

## Fixture规范

| 前缀 | 用途 | 作用域 |
|------|------|--------|
| `sample_*` | 标准测试数据 | module（只读） |
| `empty_*` | 空数据/边界测试 | function |
| `mock_*` | Mock对象 | function |
| `*_conn` | 内存数据库连接 | function |

---

## Marker 规范

### 自动标记（基于目录结构）

**项目已实现自动标记功能**：测试文件会根据其所在的目录自动添加对应的 marker。

| 目录 | 自动添加的 Marker |
|------|-----------------|
| `tests/unit/` | `@pytest.mark.unit` |
| `tests/integration/` | `@pytest.mark.integration` |

**实现原理**：
- 使用 `pytest_collection_modifyitems` hook 在测试收集时自动标记
- 配置文件位置：
  - DataHub: `packages/datahub/tests/conftest.py`
  - Foundation: `packages/foundation/tests/unit/conftest.py`

**手动标记需求**：
- ✅ `@pytest.mark.slow` - 耗时测试（需要手动标记）
- ✅ `@pytest.mark.serial` - 必须串行运行的测试
- ❌ `@pytest.mark.unit` / `@pytest.mark.integration` - 不需要手动标记

### Marker 列表

| Marker | 用途 | 运行时机 | 是否需要手动标记 |
|--------|------|----------|----------------|
| `@pytest.mark.unit` | 单元测试（完全 Mock） | 每次提交/CI | ❌ 自动标记 |
| `@pytest.mark.integration` | 集成测试（"接缝"处） | CI | ❌ 自动标记 |
| `@pytest.mark.slow` | 耗时测试 | CI/手动 | ✅ 需要手动标记 |
| `@pytest.mark.serial` | 串行测试 | CI | ✅ 需要手动标记 |
| `@pytest.mark.smoke` | 冒烟测试，核心功能 | 每次提交 | ✅ 需要手动标记 |
| `@pytest.mark.benchmark` | 性能基准测试 | 手动/定期 | ✅ 需要手动标记 |

### 使用示例

```python
# 单元测试 - 完全 Mock
@pytest.mark.unit
def test_datahub_delegates_to_calendar(mocker):
    """测试 DataHub 的委托逻辑"""
    mock_calendar = mocker.Mock()
    mock_calendar.is_trading_day.return_value = True

    hub = DataHub(calendar=mock_calendar, ...)
    result = hub.is_trading_day("2024-01-02")

    mock_calendar.is_trading_day.assert_called_once_with("2024-01-02")
    assert result is True

# 集成测试 - 测试"接缝"处
@pytest.mark.integration
def test_security_store_can_write_sqlite():
    """测试 SecurityStore 能否写入 SQLite"""
    pool = SQLitePool(":memory:", schema_path=_SCHEMA_PATH)
    pool.init_schema()

    store = SecurityStore(SQLiteClient(pool))
    store.add_security(sid=1000001, symbol="000001.SZ")

    df = store.get_by_sid(1000001)
    assert df["symbol"][0] == "000001.SZ"
```

---

## 覆盖率要求

**项目覆盖率标准（统一 80%）**：

| 指标 | 要求 | 配置位置 |
|------|------|----------|
| 分支覆盖率 | >= 80% | `pyproject.toml`: fail_under = 80 |
| CI 阈值 | >= 80% | `.github/workflows/ci.yml`: `--cov-fail-under=80` |
| 本地阈值 | >= 80% | `pixi.toml` test-cov-xml: `--cov-fail-under=80` |
| 新增代码 | >= 85% | CI 自动检查 |

### 覆盖率检查流程

```bash
# 本地开发时快速检查
pytest tests/unit/ -m "not slow" --cov

# 提交前完整检查
pytest --cov --cov-report=html --cov-report=term-missing

# 查看 HTML 报告
open htmlcov/index.html
```

---

## 运行命令

```bash
# 本地开发 - 跳过慢速和外部测试
pytest tests/unit/ -m "not slow and not external"

# 快速检查
pytest tests/unit/ -x --ff

# 冒烟测试
pytest -m smoke

# CI完整测试（跳过external）
pytest -m "not external" --cov

# 集成测试
pytest -m integration

# PIT验证测试
pytest -m pit
```

---

## 并发测试配置

**项目已配置 pytest-xdist 并发测试** (`-n auto`)：

**注意事项**：
- 测试必须独立，不能有共享状态
- 使用 `tmp_path` 而非固定路径
- 避免使用全局变量或单例

**预期提速**：2-4倍

---

## 测试隔离性

```python
# ✅ 正确：每个测试独立准备数据
def test_feature_a(store):
    store.write(sample_data_a)
    result = store.read("a")
    assert result == expected_a

def test_feature_b(store):
    store.write(sample_data_b)  # 独立准备
    result = store.read("b")
    assert result == expected_b

# ❌ 错误：依赖执行顺序
def test_feature_a(store):
    global shared_state = "a"  # 不要使用全局状态
```

---

## 可观测性测试控制

### 环境变量

```bash
# 禁用可观测性测试（默认）
export DITTO_TEST_OBSERVABILITY=disabled

# 启用可观测性测试
export DITTO_TEST_OBSERVABILITY=enabled
export DITTO_OBSERVABILITY_TEST_MODE=docker
```

### Marker 组合使用

```python
# 可观测性 + 集成测试
@pytest.mark.integration
@pytest.mark.observability
class TestObservabilityStack:
    ...
```

### 运行命令

```bash
# 跳过可观测性测试
pytest -m "not observability"

# 只运行可观测性测试
pytest -m observability
```

---

## 代码审查检查清单

提交测试代码前，确认：

### 基础规范

- [ ] 测试命名清晰描述了被测行为
- [ ] 遵循 AAA 模式
- [ ] 每个测试只验证一个行为
- [ ] 使用 fixture 而非重复代码
- [ ] Mock 只用于外部依赖
- [ ] 浮点数比较使用容差
- [ ] 边界条件有测试覆盖
- [ ] 异常路径有测试覆盖
- [ ] 无 sleep/time.sleep 等待
- [ ] 无硬编码路径或环境依赖
- [ ] 无假测试（assert True、assert False、空 pass）
- [ ] 使用参数化测试减少重复

### 🔴 目录结构强制检查

- [ ] **测试目录镜像源码目录结构**
- [ ] **源码目录重构时同步更新测试目录**
- [ ] **无 import 冲突（同名测试文件）**
- [ ] **测试文件命名符合规范**（`_unit.py` / `_integration.py`）

**源码重构时额外确认**：
- [ ] 创建源码目录 → 创建对应测试目录
- [ ] 删除源码目录 → 删除对应测试目录
- [ ] 重命名源码目录 → 重命名对应测试目录
- [ ] 移动源码文件 → 移动对应测试文件
- [ ] 合并源码目录 → 合并对应测试目录

---

## 检测问题命令（提交前必跑）

```bash
# 假测试检测
grep -r "assert True" tests/          # 假测试检测
grep -r "assert False" tests/

# import 冲突检测
pytest --collect-only 2>&1 | grep "import mismatch"  # import冲突

# 目录结构一致性检测（源码重构后必跑）
python -c "
from pathlib import Path

def check_structure(src_path, test_path, name):
    src_dirs = {d.name for d in Path(src_path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}
    test_dirs = {d.name for d in Path(test_path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}

    missing = src_dirs - test_dirs
    extra = test_dirs - src_dirs

    if missing or extra:
        print(f'❌ {name} 目录结构不一致:')
        if missing:
            print(f'   缺失测试目录: {missing}')
        if extra:
            print(f'   多余测试目录: {extra}')
        return False
    return True

all_ok = True
all_ok &= check_structure('packages/foundation/src', 'packages/foundation/tests/unit', 'Foundation')
all_ok &= check_structure('packages/datahub/src', 'packages/datahub/tests/unit', 'DataHub')
all_ok &= check_structure('apps/port/src', 'apps/port/tests/unit', 'Port')

if all_ok:
    print('✅ 所有包目录结构一致')
"

# 应迁移到 pytest-mock
grep -r "from unittest.mock" tests/
grep -r "@patch" tests/
```

---

## 完整检查命令

```bash
pixi run -e dev check             # 开发时（lint + fmt + type + test --fast）
pixi run -e dev pre-commit-run    # 提交前（pre-commit hooks）
pixi run -e dev ci                # CI 完整（lint + fmt --check + type --all + test --cov-xml）
```

---

## 类型检查（Pyright）

**配置**：
- 源码：`pyproject.toml` [tool.pyright] 段（standard + strict 模式）
- 测试：`pyright.tests.json`（basic 模式，宽松）

```bash
pixi run -e dev type          # 源码检查（strict + warnings）
pixi run -e dev type --tests  # 测试检查（basic 模式）
pixi run -e dev type --all    # 完整检查（源码 + 测试）
```

---

## 异步测试注意

```python
# ❌ 避免被pytest误识别为测试
@app.get("/api/test")
async def test_logging():  # ← 函数名以test_开头

# ✅ 重命名避免歧义
async def generate_test_logs():
```
