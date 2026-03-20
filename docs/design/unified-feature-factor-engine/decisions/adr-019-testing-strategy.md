# ADR-019: 测试策略

**状态**: 已决策（2026-03-05）

---

## 背景

因子系统需要确保算子数学正确性和物化流程可靠性，测试策略需平衡速度与覆盖。

---

## 测试分层

| 层次 | 范围 | Phase 0/1 |
|-----|------|----------|
| **单元测试** | 算子、表达式、Catalog、状态管理 | ✅ |
| **集成测试** | 物化流程、依赖解析、状态恢复 | ✅ |
| **E2E 测试** | 端到端流程 | ❌ Phase 2 |
| **属性测试** | 数学性质验证 | ❌ Phase 2 |

---

## 数据策略

| 场景 | 策略 | 说明 |
|-----|------|------|
| 小数据（<100行） | Fixtures | 预生成 Parquet/JSON 文件 |
| 大数据（>1000行） | Factory | 动态生成随机行情数据 |

```python
# tests/fixtures/market_data.py

@pytest.fixture
def small_market_df() -> pl.DataFrame:
    """小数据集 - 预定义"""
    return pl.DataFrame({
        "instrument_id": ["000001"] * 10,
        "trade_date": ["2024-01-0" + str(i) for i in range(1, 11)],
        "close": [10.0, 10.5, 11.0, 10.8, 10.2, 10.6, 11.2, 11.0, 10.9, 11.5],
    })

@pytest.fixture
def large_market_df() -> pl.DataFrame:
    """大数据集 - 动态生成"""
    return generate_market_data(
        instruments=100,
        days=250,
        seed=42,  # 可复现
    )
```

---

## 测试后端

| 组件 | 测试后端 | 说明 |
|-----|---------|------|
| SQLite（元数据） | 内存 `:memory:` | 快速、隔离 |
| Kvrocks（状态） | Mock（dict） | 单元测试无需真实 KV |
| Parquet（数据） | 临时目录 | pytest tmp_path 自动清理 |

```python
# tests/conftest.py

@pytest.fixture
def catalog_store():
    """内存 Catalog 存储"""
    client = SQLiteClient(":memory:")
    return CatalogStore(client)

@pytest.fixture
def state_store():
    """Mock 状态存储"""
    return MockStateStore({})  # dict 替代 Kvrocks
```

---

## 覆盖率目标

| 模块 | 分支覆盖率 | 理由 |
|-----|-----------|------|
| **算子** | 90%+ | 数学正确性关键 |
| **表达式引擎** | 90%+ | 核心逻辑 |
| **Service 层** | 80% | 标准要求 |
| **API 层** | 70% | 依赖集成测试 |

---

## 测试目录结构

```
packages/core/tests/
├── unit/
│   ├── operators/
│   │   ├── test_ts_functions.py      # ts_mean, ts_rank, ts_corr...
│   │   ├── test_cs_functions.py      # cs_rank, cs_zscore...
│   │   └── test_scalar_functions.py  # abs, log, sign...
│   ├── expression/
│   │   ├── test_parser.py            # 语法解析
│   │   ├── test_analyzer.py          # 语义分析
│   │   └── test_compiler.py          # 编译优化
│   ├── catalog/
│   │   ├── test_spec_store.py        # Spec CRUD
│   │   └── test_dependency_store.py  # Lineage 查询
│   └── state/
│       ├── test_sliding_window.py    # 滑动窗口
│       └── test_incremental_stats.py # 增量统计
│
└── integration/
    ├── test_materialize_flow.py      # 物化流程
    ├── test_dependency_resolution.py # 依赖排序
    └── test_state_recovery.py        # 崩溃恢复
```

---

## 典型测试示例

### 算子单元测试

```python
# tests/unit/operators/test_ts_functions.py

class TestTsMean:
    """ts_mean 单元测试"""

    def test_basic_calculation(self, small_market_df):
        """基本计算正确性"""
        result = ts_mean(small_market_df["close"], window=3)
        expected = [10.0, 10.25, 10.5, 10.77, 10.67, 10.53, 10.67, 10.93, 11.03, 11.13]
        assert np.allclose(result, expected, atol=0.01)

    def test_window_boundary(self):
        """窗口边界处理"""
        df = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
        result = ts_mean(df["value"], window=5)
        # 窗口大于数据量时，使用可用数据
        assert result[-1] == 2.0

    def test_null_handling(self):
        """NULL 值处理"""
        df = pl.DataFrame({"value": [1.0, None, 3.0, 4.0]})
        result = ts_mean(df["value"], window=2)
        # NULL 被排除，窗口内有效值计算
        assert result[-1] == 3.5
```

### 物化集成测试

```python
# tests/integration/test_materialize_flow.py

class TestMaterializeFlow:
    """物化流程集成测试"""

    def test_incremental_materialize(
        self,
        catalog_store,
        state_store,
        tmp_path,
    ):
        """增量物化流程"""
        # 1. 注册 Spec
        service = DerivedService(catalog_store, state_store, tmp_path)
        service.register_spec(SpecRegisterRequest(
            entity_type="factor",
            entity_id="test_momentum",
            expression="ts_rank(close, 5)",
        ))

        # 2. 首次物化
        result = service.materialize(MaterializeRequest(
            entity_id="test_momentum",
            mode="incremental",
        ))
        assert result.status == "success"

        # 3. 增量物化
        result2 = service.materialize(MaterializeRequest(
            entity_id="test_momentum",
            mode="incremental",
        ))
        # 幂等检查：无新数据，跳过
        assert result2.status == "skipped"
```

---

## 黄金数据集（ADR-019 扩展）

**状态**: 已决策（2026-03-12）

### 背景与目标

算子黄金数据集用于建立"数学正确性基准"，确保 Ditto 实现的算子计算结果正确且稳定。

### 数据来源策略

**定稿**：混合方案，TA-Lib 是部分 TS 算子的参考实现，不是全算子唯一基准；仓库最终提交的是去依赖化的固定黄金 fixture。

| 来源类型 | 职责 | 覆盖范围 | 说明 |
|---------|------|---------|------|
| **TA-Lib 参照** | 生成/校验黄金 fixture | SMA/EMA/RSI/MACD 等 TS 指标 | 需按 Ditto PIT 语义（closed="left"）做时间对齐 |
| **手工样本** | 主测试资产 | 边界情况 + CS/分组/标准化类算子 | TA-Lib 不覆盖的算子 |
| **固化的 fixture** | CI 运行时使用 | `tests/golden/operators/` | CI 不依赖 TA-Lib |

**关键约束**：
- TA-Lib 只用于"生成或校验黄金 fixture"，不是运行时强依赖
- 最终进仓库的是去依赖化的固定 fixture 文件

### 浮点精度处理

**定稿**：语义优先 + 混合容差（numpy.assert_allclose）+ 按算子族少量覆写

#### 核心原则

| 原则 | 要求 |
|------|------|
| **语义先行** | 窗口边界、closed、min_periods、ddof、tie 规则、null 传播必须先对齐 |
| **结构精确** | null mask / shape / dtype / 排序键 必须精确一致 |
| **容差范围** | 只用于非空浮点值，不掩盖错位或缺失模式 |
| **覆写克制** | 按"算子族"覆写，不按单个算子 |

#### 按算子族的容差策略

| 算子族 | 容差策略 | 参数 | 理由 |
|--------|---------|------|------|
| **离散/布尔/计数类** | 精确相等 | 无容差 | 无浮点误差源 |
| **归一化类** | 更依赖 atol | rtol=1e-5, atol=1e-6 | 输出接近 [0,1]，ts_rank/cs_rank 等 |
| **递归/累积型** | 适当放宽 rtol | rtol=1e-4, atol=1e-8 | 误差累积，EMA/MACD 等 |
| **通用 TS/CS 算子** | 默认 | rtol=1e-5, atol=1e-8 | ts_mean/ts_std/cs_zscore 等 |

#### 统一比较 Helper

```python
# tests/golden/helpers.py

TOLERANCE_BY_CATEGORY = {
    "discrete": None,           # 精确相等
    "normalized": (1e-5, 1e-6), # (rtol, atol)
    "recursive": (1e-4, 1e-8),
    "general": (1e-5, 1e-8),
}

def assert_golden_equal(
    actual: pl.DataFrame | np.ndarray,
    expected: pl.DataFrame | np.ndarray,
    *,
    category: Literal["discrete", "normalized", "recursive", "general"] = "general",
):
    """黄金数据集比较 helper"""
    # 1. 语义检查：shape, dtype, null mask, order
    _assert_schema_equal(actual, expected)

    if category == "discrete":
        np.testing.assert_array_equal(actual.to_numpy(), expected.to_numpy())
    else:
        rtol, atol = TOLERANCE_BY_CATEGORY[category]
        np.testing.assert_allclose(
            actual.to_numpy(),
            expected.to_numpy(),
            rtol=rtol,
            atol=atol,
            equal_nan=True
        )
```

### 覆盖率目标

**定稿**：渐进式覆盖，优先"高频 + 高风险 + 可对标"算子

#### Phase 1 算子覆盖

| 优先级 | 算子族 | 具体算子 |
|--------|--------|---------|
| **P1** | TS 核心 | ts_mean, ts_std, ts_sum, ts_rank, ts_ref |
| **P1** | CS 核心 | cs_rank, cs_zscore |
| **P2** | 递归指标 | EMA / RSI（选 1-2 个） |

#### 场景覆盖（每个算子 3-5 个）

| 场景类型 | 示例 | 必选 |
|---------|------|------|
| **正常场景** | 典型输入，标准输出 | ✅ |
| **null/缺失场景** | 含 NULL 值的序列 | ✅ |
| **边界窗口场景** | 窗口 > 数据量、窗口=1 | ✅ |
| **退化场景** | 常数列、单值、ties | ✅ |
| **极端值场景** | 极大/极小值 | 可选 |

#### 职责边界

| 测试类型 | 职责 |
|---------|------|
| **黄金数据集** | 验证"给定输入，输出数学结果是否正确且稳定" |
| **单元测试** | 非法参数 / 应抛错的异常场景 |

### 目录结构

```
tests/golden/
├── operators/
│   ├── ts_mean/
│   │   ├── normal.parquet       # 正常场景
│   │   ├── nulls.parquet        # null 处理
│   │   ├── boundary.parquet     # 边界窗口
│   │   └── degenerate.parquet   # 退化场景
│   ├── ts_rank/
│   ├── ts_std/
│   ├── cs_rank/
│   └── ...
├── helpers.py                   # 比较 helper
└── conftest.py                  # fixture 加载
```
