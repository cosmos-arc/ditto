---
last_synced: 2026-06-04
---

# Analysis Agent 指南

## 定位

纯研究分析平面 — 研究数据集契约、研究 control-plane。`experiments` 已提供纯领域合同；reports/diagnostics/screeners 仍为 reserved namespace。

## 核心模块

| 模块 | 职责 |
|------|------|
| contracts.py | research catalog reader/writer protocols |
| errors.py | 分析层错误类型 |
| research/ | 研究 control-plane（domain/catalog_service/artifact_service） |
| experiments/ | experiment identity/spec/state/protocol 纯领域合同；不含调度与存储实现 |
| storage/sqlite/research/ | 研究 SQLite 存储（reader/writer） |
| di/ | analysis DI providers |

## 依赖规则

### 允许

- analysis → kernel ✅
- analysis → platform ✅

### 禁止

- analysis → data/features/strategy/portfolio/risk/execution/backtest ❌
- 生产能力包 → analysis ❌（application 仅 research query 与 experiment 编排路径可消费合同）
- 使用 reports/diagnostics/screeners 作为行为依赖 ❌
- 把 experiments 合同误当作调度、I/O 或存储实现 ❌

## 关键约束

- 研究存储使用独立 SQLite，不与生产存储混合
- application 可在 research experiment 编排路径消费 experiments 合同；apps 必须经 application facade/composition 使用
- root barrel 只重导出 AnalysisError、ResearchDatasetError、ResearchDatasetSpec

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
