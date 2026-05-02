# Analysis 层架构规范

## 定位

Analysis 是**纯研究分析平面**，负责：
- 研究数据集管理（artifact、catalog）
- 报告生成（reports）
- 诊断工具（diagnostics）
- 实验管理（experiments）
- 筛选器（screeners）

**核心原则**：
- 纯研究层，不被生产路径依赖
- 生产包（strategy/portfolio/risk/execution/backtest/application）禁止导入 analysis
- 只有 apps 层的研究入口（jobs/api）可以调用 analysis
- 研究存储使用独立 SQLite，不与生产存储混合

## 允许依赖

```
ditto_analysis → ditto_kernel ✅
ditto_analysis → ditto_data ✅
ditto_analysis → ditto_features ✅
```

外部依赖：polars, numpy, orjson

## 禁止依赖

```
ditto_analysis → ditto_strategy ❌
ditto_analysis → ditto_portfolio ❌
ditto_analysis → ditto_risk ❌
ditto_analysis → ditto_execution ❌
ditto_analysis → ditto_backtest ❌
ditto_analysis → ditto_application ❌
ditto_analysis → ditto_apps ❌
```

## 内部目录职责

```
ditto_analysis/
├── research/             # 研究数据集管理
│   ├── domain.py         # 研究领域模型
│   ├── catalog_service.py    # 研究目录服务
│   └── artifact_service.py   # 研究产物服务
├── reports/              # 报告生成（待扩展）
├── diagnostics/          # 诊断工具（待扩展）
├── experiments/          # 实验管理（待扩展）
├── screeners/            # 筛选器（待扩展）
└── storage/
    └── sqlite/
        └── research/     # 研究 SQLite 存储
            ├── reader.py
            └── writer.py
```

## 测试位置

```
packages/analysis/tests/
└── unit/
    └── test_research_unit.py
```

## 典型导入示例

```python
# 研究服务
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.artifact_service import ResearchArtifactService

# 研究领域模型
from ditto_analysis.research.domain import ResearchDataset

# 研究存储
from ditto_analysis.storage.sqlite.research.reader import ResearchReader
from ditto_analysis.storage.sqlite.research.writer import ResearchWriter
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type packages/analysis/src
pixi run -e dev arch-check
```
