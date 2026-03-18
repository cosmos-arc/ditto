# 2026-03-14 Unified Feature Factor Engine Phase 6 Hardening Plan

## 1. 当前状态

截至 2026 年 3 月 14 日，unified-feature-factor-engine 的 v1 主链已经具备：

1. artifact-backed query
2. durable materialization + invalidation cascade
3. legacy catalog migration
4. research dataset build
5. publication safety / shadow compare / certify / promote / rollback / deprecate
6. 四条专项 integration tests
7. 首版 benchmark harness：[`scripts/benchmarks/derived_benchmark.py`](../../scripts/benchmarks/derived_benchmark.py)

本阶段的目标不再是扩功能，而是把“功能闭环”推进到“性能与运维闭环”。

---

## 2. 本地基线环境

2026 年 3 月 14 日本地开发环境快照：

| 项目 | 值 |
|------|----|
| OS | `Linux 6.6.87.2-microsoft-standard-WSL2` |
| CPU | `6 vCPU` |
| Memory | `12,249,832 kB` |
| Command | `pixi run -e dev python scripts/benchmarks/derived_benchmark.py --scale S --scale M --iterations 3` |
| Command | `pixi run -e dev python scripts/benchmarks/derived_benchmark.py --scale L --iterations 1` |

本地基线结果已经同步回 ADR-037，作为 Phase 1 v1 的初始 benchmark snapshot。

---

## 3. Phase 6 目标

### 3.1 Benchmark / Regression Budget

1. 固化 `query / materialize / shadow_compare` 三类 workload。
2. 把 `materialize(S/M)` 与 `shadow_compare(S/M)` 纳入 PR regression gate。
3. 把 `query(S/M)` 与全部 `L` workload 保留为 warning/observe only。

### 3.2 SLO 收敛

1. Phase 1 保留相对回归预算，不直接承诺正式 P50/P95/P99 数值。
2. 补端到端时间戳，把 `trigger -> materialize_done` 与 `invalidation_enqueued -> downstream_done` 做成真实运行时 SLI。
3. 连续积累 2 周以上 benchmark + runtime histogram 后，再升级为 Phase 2 正式 SLO。

### 3.3 运维闭环

1. rebuild runbook：全量重建、单 derived 重建、按 dependency ref 重建。
2. DR / restore runbook：catalog / artifacts / publication runtime 的恢复顺序。
3. retention housekeeping：过期 shadow reports、旧 artifact、过期 checkpoints 的清理规则。
4. dashboard / alerting：慢物化、级联堆积、publication certify 失败率、research build 失败率。

---

## 4. 执行批次

### Batch H1: Benchmark 治理

1. 把 benchmark 脚本接入 nightly 或手工 perf pipeline。
2. 约定 baseline 存储位置（建议专用 artifact bucket 或 Git LFS）。
3. 增加基线 diff 命令，输出 `pass / warning / error` 分类。

### Batch H2: Runtime SLI 落库

1. 为 materialization run record 增加端到端起止时间。
2. 为 invalidation cascade 增加 enqueue / downstream done 时间戳。
3. 输出 histogram-ready 指标，打通监控面板。

### Batch H3: Housekeeping

1. 实现旧 shadow report / publication runtime 数据清理。
2. 实现 artifact retention 与 orphan checkpoint 清理。
3. 定义研究数据集 snapshot 保留策略与清理窗口。

### Batch H4: Release Hardening

1. 跑一次完整 dry-run：materialize -> shadow compare -> certify -> promote -> rollback。
2. 形成运维 runbook。
3. 确认 Phase 2 SLO 收敛入口和责任人。

---

## 5. 验收标准

本计划完成时，至少满足：

1. benchmark baseline 可重复生成，且有明确更新流程。
2. PR 能阻断 `materialize(S/M)` 与 `shadow_compare(S/M)` 的明显退化。
3. 运行时端到端 SLI 已落库，可用于 P50/P95/P99 收敛。
4. rebuild / DR / retention 有书面 runbook 与可执行入口。
5. 发布、回滚、研究数据集构建都具备最小运维说明。

---

## 6. 建议命令

```bash
pixi run -e dev pytest -n0 --no-cov packages/core/tests/benchmarks/test_derived_benchmarks.py -v
pixi run -e dev python scripts/benchmarks/derived_benchmark.py --scale S --scale M --iterations 3
pixi run -e dev python scripts/benchmarks/derived_benchmark.py --scale L --iterations 1
pixi run -e dev check
pixi run -e dev arch-check
```
