---
last_synced: 2026-06-04
---

# Analysis Agent 指南

## 定位

纯研究分析平面 — 研究数据集契约、研究 control-plane。reports/diagnostics/experiments/screeners 为 reserved namespace，当前无 public runtime API。

## 核心模块

| 模块 | 职责 |
|------|------|
| contracts.py | research catalog reader/writer protocols |
| errors.py | 分析层错误类型 |
| research/ | 研究 control-plane（domain/catalog_service/artifact_service） |
| storage/sqlite/research/ | 研究 SQLite 存储（reader/writer） |
| di/ | analysis DI providers |

## 依赖规则

### 允许

- analysis → kernel ✅
- analysis → platform ✅

### 禁止

- analysis → data/features/strategy/portfolio/risk/execution/backtest ❌
- 生产包 → analysis ❌（application 只有 research query 路径可使用）
- 使用 reports/diagnostics/experiments/screeners 作为行为依赖 ❌

## 关键约束

- 研究存储使用独立 SQLite，不与生产存储混合
- application/apps 仅 research query/facade/DI wiring 可使用 analysis
- root barrel 只重导出 AnalysisError、ResearchDatasetError、ResearchDatasetSpec

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
