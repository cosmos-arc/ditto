> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 研究环境使用说明

**版本：v2.0 Final**

**日期：2025-12-08**

---

## 1. 概述

本文档描述 Ditto 的研究环境（Research Playground）设计和使用规范，确保：

1. 研究代码与生产代码分离
2. 实验可复现
3. 研究成果能顺利转化为生产代码
4. 数据安全（只读访问生产数据）

---

## 2. 目录结构

```
research/
├── notebooks/                    # Jupyter Notebook
│   ├── exploration/             # 探索性分析
│   │   ├── 001_data_overview.ipynb
│   │   └── 002_etf_correlation.ipynb
│   ├── factors/                 # 因子研究
│   │   ├── 001_rs_factor_analysis.ipynb
│   │   └── 002_value_factor_pit.ipynb
│   ├── regime/                  # Regime 研究
│   │   └── 001_regime_threshold_analysis.ipynb
│   └── backtest/                # 回测分析
│       ├── 001_baseline_backtest.ipynb
│       └── 002_cost_sensitivity.ipynb
│
├── experiments/                  # 正式实验
│   ├── EXP_001_rs_window/       # 实验：RS 窗口期研究
│   │   ├── config.yaml          # 实验配置
│   │   ├── run.py               # 运行脚本
│   │   ├── results/             # 结果输出
│   │   └── README.md            # 实验说明
│   └── EXP_002_regime_adaptive/
│       └── ...
│
├── reports/                      # 研究报告
│   ├── 2024-12/
│   │   ├── factor_analysis_report.md
│   │   └── regime_threshold_report.md
│   └── templates/
│       ├── factor_report_template.md
│       └── experiment_report_template.md
│
├── specs/                        # 策略/因子规格书
│   ├── SPEC_rs_factor_v1.md
│   └── SPEC_rotation_strategy_v1.md
│
├── archive/                      # 归档（不再活跃的研究）
│
├── data/                         # 研究专用数据（如有）
│   └── external/                # 外部数据集
│
└── README.md                     # 研究环境说明
```

---

## 3. 数据访问规范

### 3.1 只读访问原则

研究环境**只能读取**生产数据，不能写入：

```python
# research/utils/data_access.py

import duckdb
from pathlib import Path

class ResearchDataAccess:
    """研究环境的数据访问（只读）"""

    def __init__(self, warehouse_path: str = "../data/warehouse.duckdb"):
        # 只读模式连接
        self.conn = duckdb.connect(warehouse_path, read_only=True)

    def query(self, sql: str) -> pl.DataFrame:
        """执行查询"""
        return self.conn.execute(sql).pl()

    def get_etf_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "hfq"
    ) -> pl.DataFrame:
        """获取 ETF K线（动态复权）"""
        raw = self.query(f"""
            SELECT k.*, a.adj_factor
            FROM etf_kline_daily k
            LEFT JOIN etf_adj_factor a
              ON k.symbol = a.symbol AND k.trade_date = a.trade_date
            WHERE k.symbol = '{symbol}'
              AND k.trade_date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY k.trade_date
        """)

        if adjust == "none":
            return raw
        return self._apply_adjustment(raw, adjust)
```

### 3.2 研究数据存储

研究产生的中间数据存储在 `research/data/` 下：

```python
# 保存研究数据
results.write_parquet("research/data/experiment_results/exp001_results.parquet")

# 不要写入生产数据目录
# results.write_parquet("data/warehouse/...")  # 禁止！
```

---

## 4. Notebook 规范

### 4.1 命名规范

```
{序号}_{简短描述}.ipynb

示例：
001_data_overview.ipynb
002_rs_factor_window_analysis.ipynb
003_regime_threshold_sensitivity.ipynb
```

### 4.2 Notebook 结构

每个 Notebook 应包含以下章节：

```markdown
# [Notebook 标题]

## 1. 背景与目标
- 研究问题是什么？
- 期望得到什么结论？

## 2. 数据准备
- 使用什么数据？
- 数据时间范围？

## 3. 分析过程
- 具体的分析步骤
- 可视化结果

## 4. 结论
- 主要发现是什么？
- 是否支持假设？

## 5. 后续行动
- 是否需要进入正式实验？
- 是否可以直接应用到生产？
```

### 4.3 代码规范

```python
# Notebook 第一个 Cell：环境配置
# pixi 会自动配置 editable packages，无需手动添加路径

import polars as pl
import matplotlib.pyplot as plt
from research.utils.data_access import ResearchDataAccess

# 配置
%matplotlib inline
plt.style.use('seaborn-v0_8-whitegrid')

# 数据连接（只读）
data = ResearchDataAccess()
```

```python
# 好的实践：明确说明参数
RS_WINDOW = 20  # 相对强弱计算窗口
START_DATE = "2020-01-01"
END_DATE = "2024-12-01"
UNIVERSE = ["510300.SH", "510500.SH", "512000.SH"]
```

---

## 5. 正式实验规范

### 5.1 实验目录结构

```
experiments/
└── EXP_001_rs_window/
    ├── config.yaml          # 实验配置
    ├── run.py               # 运行脚本
    ├── analysis.py          # 分析脚本
    ├── results/             # 结果输出
    │   ├── metrics.json     # 量化指标
    │   ├── figures/         # 图表
    │   └── raw/             # 原始结果
    ├── README.md            # 实验说明
    └── CONCLUSION.md        # 实验结论
```

### 5.2 实验配置模板 (config.yaml)

```yaml
# EXP_001: RS 因子窗口期研究
experiment:
  id: "EXP_001"
  name: "RS Factor Window Analysis"
  author: "your_name"
  created_at: "2024-12-08"
  status: "completed"  # draft / running / completed / archived

hypothesis:
  description: "RS 因子的最优窗口期在 15-25 天之间"
  expected_outcome: "20天窗口的 IC 最高"

data:
  source: "warehouse.duckdb"
  start_date: "2020-01-01"
  end_date: "2024-12-01"
  universe: "etf_universe_core"

parameters:
  rs_windows: [10, 15, 20, 25, 30, 40, 60]
  ic_lookback: 20  # IC 计算的未来收益期

metrics:
  - name: "ic_mean"
    description: "平均 Rank IC"
  - name: "ic_ir"
    description: "IC 的 Information Ratio"
  - name: "ic_positive_ratio"
    description: "IC 为正的比例"

reproducibility:
  random_seed: 42
  data_version: "v1_2020_2024q4"
```

### 5.3 实验运行脚本模板 (run.py)

```python
#!/usr/bin/env python
"""
实验：RS 因子窗口期分析
运行：python run.py
"""

import yaml
import json
from pathlib import Path
from datetime import datetime
import polars as pl

# 加载配置
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# 设置随机种子（如有）
import random
random.seed(config["reproducibility"]["random_seed"])

# 数据加载
from research.utils.data_access import ResearchDataAccess
data = ResearchDataAccess()

# 实验逻辑
def run_experiment():
    results = []

    for window in config["parameters"]["rs_windows"]:
        print(f"Testing window = {window}")

        # 计算因子
        factor_df = calc_rs_factor(data, window)

        # 计算 IC
        ic_series = calc_rank_ic(factor_df, config["parameters"]["ic_lookback"])

        results.append({
            "window": window,
            "ic_mean": ic_series.mean(),
            "ic_std": ic_series.std(),
            "ic_ir": ic_series.mean() / ic_series.std() if ic_series.std() > 0 else 0,
            "ic_positive_ratio": (ic_series > 0).mean()
        })

    return pl.DataFrame(results)

def calc_rs_factor(data, window):
    # 实现...
    pass

def calc_rank_ic(factor_df, lookback):
    # 实现...
    pass

# 主函数
if __name__ == "__main__":
    print(f"Starting experiment: {config['experiment']['id']}")
    print(f"Time: {datetime.now()}")

    # 运行实验
    results = run_experiment()

    # 保存结果
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    results.write_json(results_dir / "metrics.json")
    results.write_csv(results_dir / "metrics.csv")

    # 打印摘要
    print("\nResults Summary:")
    print(results)

    print(f"\nExperiment completed at {datetime.now()}")
```

### 5.4 实验结论模板 (CONCLUSION.md)

```markdown
# 实验结论：EXP_001 RS 因子窗口期分析

## 实验摘要
- 实验 ID：EXP_001
- 完成日期：2024-12-08
- 数据范围：2020-01-01 至 2024-12-01

## 主要发现

### 1. IC 分析结果
| 窗口期 | IC均值 | IC_IR | IC正比例 |
|--------|--------|-------|----------|
| 10     | 0.025  | 0.45  | 58%      |
| 15     | 0.032  | 0.52  | 61%      |
| 20     | 0.038  | 0.58  | 64%      |
| 25     | 0.035  | 0.54  | 62%      |
| 30     | 0.028  | 0.48  | 59%      |

### 2. 结论
- **假设验证**：支持。20天窗口的 IC 最高（0.038）。
- **最优参数**：推荐使用 20 天窗口。
- **稳健性**：15-25 天窗口的表现相近，参数较为稳健。

## 行动建议
- [ ] 将 RS_WINDOW=20 写入生产配置
- [ ] 编写 RS 因子规格书 (SPEC)
- [ ] 进入因子健康度监控

## 附录
- 完整结果：results/metrics.json
- 图表：results/figures/
```

---

## 6. 从研究到生产的流程

### 6.1 完整流程

```
1. 探索性分析 (Notebook)
   │
   │ 发现有价值的想法
   ▼
2. 正式实验 (experiments/)
   │
   │ 验证假设，量化结果
   ▼
3. 编写规格书 (specs/)
   │
   │ 明确接口、参数、验收标准
   ▼
4. 实现生产代码 (packages/engine/, packages/analytics/)
   │
   │ 按规格书实现
   ▼
5. 对齐测试
   │
   │ 确保研究结果与生产一致
   ▼
6. 部署 & 监控
```

### 6.2 规格书模板 (specs/)

```markdown
# 规格书：RS 因子 v1

## 1. 概述
- 名称：相对强弱因子 (RS Factor)
- 版本：v1.0
- 作者：[name]
- 基于实验：EXP_001

## 2. 定义
相对强弱因子 = ETF 收益率 - 基准收益率

## 3. 参数
| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| window | 20 | 10-60 | 计算窗口（交易日） |
| benchmark | 000300.SH | - | 基准指数 |

## 4. 接口
```python
class RSFactor(Factor):
    def __init__(self, window: int = 20, benchmark: str = "000300.SH"):
        ...

    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        """计算 RS 因子

        Returns:
            DataFrame with columns: symbol, trade_date, rs_value, rs_zscore
        """
        ...
```

## 5. PIT 安全
- 只使用 trade_date 当日可知的价格数据
- knowledge_date = trade_date

## 6. 验收标准
- [ ] 与实验结果的 IC 差异 < 0.001
- [ ] 回测结果一致
- [ ] 单元测试通过

## 7. 监控指标
- 6M IC > 0.02
- 12M IC > 0
- IC 月度衰减 < 2%
```

### 6.3 对齐验证

研究代码与生产代码必须对齐：

```python
# tests/test_research_production_alignment.py

def test_rs_factor_alignment():
    """验证研究代码与生产代码的 RS 因子结果一致"""

    # 研究代码计算
    from research.factors.rs_factor import calc_rs_research
    research_result = calc_rs_research(universe, trade_date)

    # 生产代码计算
    from ditto.engine.factor_engine import RSFactor
    production_result = RSFactor(window=20).calc(ctx)

    # 对齐验证
    merged = research_result.join(production_result, on=["symbol", "trade_date"])
    diff = (merged["rs_research"] - merged["rs_production"]).abs().max()

    assert diff < 1e-6, f"RS factor alignment failed: max diff = {diff}"
```

---

## 7. 研究报告规范

### 7.1 报告模板

```markdown
# [报告标题]

**作者**：[name]
**日期**：[date]
**状态**：Draft / Review / Final

## 执行摘要
[1-2 段总结关键发现和建议]

## 1. 背景与目标
- 研究问题
- 业务背景
- 预期目标

## 2. 数据与方法
- 数据来源
- 时间范围
- 分析方法

## 3. 分析结果
- 主要发现（配图表）
- 统计显著性

## 4. 结论与建议
- 核心结论
- 行动建议
- 后续研究方向

## 5. 附录
- 详细数据
- 代码参考
```

### 7.2 图表规范

```python
import matplotlib.pyplot as plt

# 统一样式
plt.style.use('seaborn-v0_8-whitegrid')

def plot_ic_series(ic_series, title):
    """绘制 IC 时序图"""
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.bar(ic_series.index, ic_series.values,
           color=['green' if v > 0 else 'red' for v in ic_series.values],
           alpha=0.7)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.axhline(y=ic_series.mean(), color='blue', linestyle='--',
               label=f'Mean: {ic_series.mean():.3f}')

    ax.set_title(title)
    ax.set_xlabel('Date')
    ax.set_ylabel('Rank IC')
    ax.legend()

    plt.tight_layout()
    return fig

# 保存图表
fig = plot_ic_series(ic_series, "RS Factor IC (Window=20)")
fig.savefig("results/figures/rs_ic_series.png", dpi=150)
```

---

## 8. 最佳实践

### 8.1 Do's（推荐）

- ✅ 每个实验有独立目录和配置文件
- ✅ 实验可复现（记录数据版本、随机种子）
- ✅ 探索性分析在 Notebook，正式实验在 experiments/
- ✅ 研究成果转化为规格书
- ✅ 定期归档不活跃的研究

### 8.2 Don'ts（禁止）

- ❌ 研究代码直接修改生产数据库
- ❌ Notebook 中硬编码绝对路径
- ❌ 跳过规格书直接写生产代码
- ❌ 不记录实验配置和结论
- ❌ 使用未版本化的数据集

---

## 9. 快速开始

```bash
# 1. 进入研究目录
cd research

# 2. 启动 Jupyter
pixi run jupyter lab

# 3. 创建新 Notebook
# 在 notebooks/exploration/ 下创建

# 4. 使用数据访问工具
from research.utils.data_access import ResearchDataAccess
data = ResearchDataAccess()

# 5. 开始探索！
df = data.get_etf_kline("510300.SH", "2020-01-01", "2024-12-01")
```

---

*本研究环境规范将随项目实践持续更新。保持研究的严谨性和可复现性。*
