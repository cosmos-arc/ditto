# 国债收益率与美元指数数据接入实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 接入 FRED 贸易加权美元指数（DTWEXBGS）和 Tushare 中国国债收益率曲线（yc_cb），保持中美债券收益率口径一致（到期收益率）

**Architecture:**
- FRED: 复用现有 `MacroFredAdapter` + `FredIndicator` 机制，新增 DTWEXBGS 指标定义
- Tushare: 新增 `BondYieldTushareAdapter` 专门处理国债收益率曲线（yc_cb 接口返回多期限数据，需要特殊处理）

**Tech Stack:** polars, fredapi, tushare

---

## Task 1: FRED 添加贸易加权美元指数 DTWEXBGS

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/fred/indicators.py`

**Step 1: 添加 DTWEXBGS 指标定义**

在 `FRED_INDICATORS` 字典中新增 `dollar_index` 类别和 DTWEXBGS 指标：

```python
# 在 CategoryType 中添加新类别
CategoryType = Literal[
    "economic",
    "prices",
    "money_supply",
    "employment",
    "credit",
    "survey",
    "interest_rate",
    "commodity",
    "vix",
    "dollar_index",  # 新增
]

# 在 FRED_INDICATORS 中添加
"US_DOLLAR_INDEX_BROAD": FredIndicator(
    series_id="DTWEXBGS",
    code="US_DOLLAR_INDEX_BROAD",
    name="美国贸易加权美元指数(广义)",
    category="dollar_index",
    frequency="daily",
    unit="指数",
    description="Trade Weighted U.S. Dollar Index: Broad, Goods and Services",
    need_pit=False,
),
```

**Step 2: 验证**

运行测试确认指标定义正确：
```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/fred/ -v -k "indicator"
```

---

## Task 2: Tushare 添加中国国债收益率数据

**Files:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py`
- Create: `packages/datahub/tests/unit/sources/tushare/adapters/test_bond_yield.py`
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/__init__.py`

**Step 1: 定义国债收益率指标映射**

创建新文件 `bond_yield.py`，定义中国国债收益率的指标映射：

```python
"""Tushare bond yield curve adapter."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class CnBondYieldIndicator:
    """中国国债收益率指标定义"""
    code: str           # 统一指标代码，如 CN_BOND_YIELD_1Y
    field: str          # yc_cb 返回的字段名，如 y1
    name: str           # 中文名称
    maturity: str       # 期限描述
    description: str    # 描述

# 国债收益率指标映射（到期收益率，curve_type=0）
CN_BOND_YIELD_INDICATORS: dict[str, CnBondYieldIndicator] = {
    "CN_BOND_YIELD_1Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_1Y",
        field="y1",
        name="中国1年期国债收益率",
        maturity="1年",
        description="中债国债收益率曲线1年期（到期收益率）",
    ),
    "CN_BOND_YIELD_2Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_2Y",
        field="y2",
        name="中国2年期国债收益率",
        maturity="2年",
        description="中债国债收益率曲线2年期（到期收益率）",
    ),
    "CN_BOND_YIELD_5Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_5Y",
        field="y5",
        name="中国5年期国债收益率",
        maturity="5年",
        description="中债国债收益率曲线5年期（到期收益率）",
    ),
    "CN_BOND_YIELD_10Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_10Y",
        field="y10",
        name="中国10年期国债收益率",
        maturity="10年",
        description="中债国债收益率曲线10年期（到期收益率）",
    ),
}
```

**Step 2: 实现 BondYieldTushareAdapter**

```python
class BondYieldTushareAdapter(BaseTushareAdapter):
    """Tushare 国债收益率曲线适配器"""

    @traced("source.tushare.fetch_bond_yield")
    def fetch_bond_yield(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        获取中国国债收益率曲线数据

        Args:
            codes: 指标代码列表（如 ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns
        """
        # 1. 过滤有效的指标代码
        # 2. 调用 yc_cb 接口（ts_code='1001.CB', curve_type='0'）
        # 3. 将多期限字段（y1, y2, y5, y10）转换为多行
        # 4. 转换为 MACRO_INDICATOR_SOURCE_SCHEMA 格式
```

**Step 3: yc_cb 接口调用示例**

```python
response = self._client.query(
    api_name="yc_cb",
    fields="ts_code,trade_date,curve_type,y1,y2,y5,y10",
    ts_code="1001.CB",      # 中债国债收益率曲线
    curve_type="0",          # 0=到期收益率
    start_date="20240101",
    end_date="20241231",
)
```

**Step 4: 数据转换逻辑**

yc_cb 返回格式（宽表）：
```
trade_date  | y1   | y2   | y5   | y10
20240101    | 2.1  | 2.3  | 2.5  | 2.7
```

需要转换为长表格式（MACRO_INDICATOR_SOURCE_SCHEMA）：
```
indicator_code    | date       | value | ...
CN_BOND_YIELD_1Y  | 2024-01-01 | 2.1   | ...
CN_BOND_YIELD_2Y  | 2024-01-01 | 2.3   | ...
CN_BOND_YIELD_5Y  | 2024-01-01 | 2.5   | ...
CN_BOND_YIELD_10Y | 2024-01-01 | 2.7   | ...
```

**Step 5: 更新 __init__.py**

```python
from ditto_datahub.sources.tushare.adapters.bond_yield import (
    BondYieldTushareAdapter,
    CN_BOND_YIELD_INDICATORS,
)

__all__ = [
    # ...existing...
    "BondYieldTushareAdapter",
    "CN_BOND_YIELD_INDICATORS",
]
```

**Step 6: 编写单元测试**

```python
# test_bond_yield.py
class TestBondYieldTushareAdapter:
    def test_cn_bond_yield_indicators_exist(self):
        """验证指标定义存在"""
        assert "CN_BOND_YIELD_1Y" in CN_BOND_YIELD_INDICATORS
        assert "CN_BOND_YIELD_10Y" in CN_BOND_YIELD_INDICATORS

    def test_fetch_bond_yield_basic(self, mock_client):
        """测试基本数据获取"""
        # mock yc_cb 响应
        # 验证返回的 DataFrame 格式正确

    def test_fetch_bond_yield_wide_to_long_transform(self, mock_client):
        """测试宽表到长表转换"""
        # 验证多期限字段正确转换为多行
```

---

## Task 3: 集成测试

**Files:**
- Create: `packages/datahub/tests/integration/sources/fred/test_dollar_index.py`
- Create: `packages/datahub/tests/integration/sources/tushare/test_bond_yield.py`

**Step 1: FRED DTWEXBGS 集成测试**

```python
def test_fetch_dtwexbgs(fred_client):
    """测试获取贸易加权美元指数"""
    adapter = MacroFredAdapter()
    df = adapter.fetch_indicators(
        codes=["US_DOLLAR_INDEX_BROAD"],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    assert df.height > 0
    assert "US_DOLLAR_INDEX_BROAD" in df["indicator_code"].unique()
```

**Step 2: Tushare 国债收益率集成测试**

```python
def test_fetch_cn_bond_yield(tushare_client):
    """测试获取中国国债收益率"""
    adapter = BondYieldTushareAdapter()
    df = adapter.fetch_bond_yield(
        codes=["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    assert df.height > 0
    assert set(df["indicator_code"].unique()) == {"CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"}
```

---

## Task 4: 文档更新

**Files:**
- Modify: `docs/research/tushare-fx-commodity-research.md` 或创建新文档

**Step 1: 更新数据源文档**

添加新数据源的说明：
- DTWEXBGS：贸易加权美元指数（26种货币）
- CN_BOND_YIELD_1Y/2Y/5Y/10Y：中国国债收益率（到期收益率）

---

## 数据口径说明

### 债券收益率口径

| 指标 | 数据源 | 口径 | 说明 |
|------|--------|------|------|
| 美国国债收益率 | FRED | 到期收益率 | DGS系列，市场惯例 |
| 中国国债收益率 | Tushare | 到期收益率 | yc_cb curve_type=0 |
| 贸易加权美元指数 | FRED | - | DTWEXBGS，26种货币 |

### instrument_id 分配（如需）

| 数据类型 | instrument_id 范围 |
|----------|-------------------|
| 贸易加权美元指数 | 4_100_001 |
| 中国国债收益率 | 6_000_001 - 6_000_004 |

---

## 验收标准

- [ ] FRED DTWEXBGS 指标定义正确，可通过 `MacroFredAdapter` 获取
- [ ] Tushare `BondYieldTushareAdapter` 可获取 1/2/5/10 年期国债收益率
- [ ] 数据格式符合 `MACRO_INDICATOR_SOURCE_SCHEMA`
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试通过
- [ ] 文档已更新

---

## 注意事项

1. **yc_cb 接口需要积分**：确认 Tushare 账号有足够积分访问此接口
2. **时区处理**：中国国债收益率数据日期为北京时间
3. **knowledge_date**：国债收益率数据 T+0 发布，knowledge_date = date
4. **口径一致**：中美债券收益率统一使用到期收益率，便于比较分析
