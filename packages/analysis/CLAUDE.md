# Analysis 层架构规范

## 定位

Analysis 是**纯研究分析平面**，负责：
- 研究数据集契约（research dataset contracts）
- 分析层错误类型（analysis errors）
- 研究 control-plane 的 contracts/domain/services/storage/DI

root package barrel（`from ditto_analysis import ...`）只重导出 `AnalysisError`、`ResearchDatasetError` 与 `ResearchDatasetSpec`。

当前已实现的 analysis runtime surface 还包括 research control-plane contracts/domain/services/storage/DI，例如：
- `ditto_analysis.research.*`
- `ditto_analysis.contracts`
- `ditto_analysis.di`
- `ditto_analysis.storage.sqlite.research`

`reports`、`diagnostics`、`experiments`、`screeners` 是 reserved/future product namespaces；当前无 public runtime API。不得将它们视为已实现能力，也不得作为运行时行为依赖使用。

**核心原则**：
- Analysis 自身不依赖 application/apps/生产域包
- 生产域包 data/features/strategy/portfolio/risk/execution/backtest 禁止导入 analysis
- application 只有 research query/facade/DI wiring 可以使用 analysis
- apps 只有 research jobs/api/registry composition 入口可以使用 analysis
- application/apps 不得把 `reports`、`diagnostics`、`experiments`、`screeners` 当行为依赖
- 研究存储使用独立 SQLite，不与生产存储混合

## 允许依赖

```
ditto_analysis → ditto_kernel ✅
ditto_analysis → ditto_platform ✅
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

## 反向导入边界

当前治理由两类门禁共同执行：

`.importlinter` broad contracts：
- `production-no-analysis` 禁止 data/features/strategy/portfolio/risk/execution/backtest 导入 `ditto_analysis`
- `analysis-no-production-dependency` 禁止 `ditto_analysis` 依赖 data/features/strategy/portfolio/risk/execution/backtest/application/apps
- `layered-architecture` 允许 apps/application 作为上层组合 analysis；它不负责 application/apps 的细粒度 research-only 路径约束

`scripts/architecture/check_architecture_smells.py` 细粒度约束：
- `check_production_no_analysis` 将 `ditto_application` 纳入生产路径扫描，仅 allowlist application provider wiring 与 exact research query 路径导入 `ditto_analysis`
- `check_apps_non_registry_capability_imports` 禁止 apps 非 registry/composition 模块直接导入 capability internals；apps 应通过 application facades 或 registry composition 使用 analysis
其中 production→analysis wiring 豁免以 `PRODUCTION_ANALYSIS_WIRING_ALLOWANCES` 作为 enforcement source；当前只覆盖 application provider/research query 路径，并且每条必须带 owner/reason。

架构策略：
- application/apps 不得把 `reports`、`diagnostics`、`experiments`、`screeners` 当行为依赖
- 当前没有专门扫描这些 reserved namespace 的 use-site checker；治理依赖 placeholder honesty checker 保持命名空间诚实，并依赖上述导入边界限制 capability 直连范围

## 内部目录职责

```
ditto_analysis/
├── contracts.py          # research catalog reader/writer protocols
├── errors.py             # 分析层错误类型
├── di/                   # analysis DI providers
│   ├── _factory.py       # DI 工厂
│   └── storage.py        # 存储层 DI Provider
├── research/             # 研究 control-plane domain/services
│   ├── domain.py         # 研究领域模型
│   ├── catalog_service.py    # 研究目录服务
│   └── artifact_service.py   # 研究产物服务
├── reports/              # reserved/future product namespace；当前无 public runtime API
├── diagnostics/          # reserved/future product namespace；当前无 public runtime API
├── experiments/          # reserved/future product namespace；当前无 public runtime API
├── screeners/            # reserved/future product namespace；当前无 public runtime API
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
# root package barrel 只重导出这三项
from ditto_analysis import AnalysisError, ResearchDatasetError, ResearchDatasetSpec

# 已实现 runtime surface 可按子模块导入
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.contracts import ResearchCatalogReaderProtocol
from ditto_analysis.di import get_analysis_providers

# 保留命名空间不得作为现有能力或运行时行为依赖
# from ditto_analysis import reports, diagnostics, experiments, screeners
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type packages/analysis/src
pixi run -e dev arch-check
```
