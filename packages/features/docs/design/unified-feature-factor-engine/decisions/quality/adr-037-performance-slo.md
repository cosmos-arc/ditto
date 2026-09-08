> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-037: 性能 SLO 定义

**状态**: 已决策（2026-03-12）

---

## 背景

因子系统需要明确的性能基准和 SLO，用于容量规划、回归检测和运维保障。

---

## Phase 1 SLO 策略

### 决策

**D-1**: Phase 1 不承诺正式 SLO 数值，先定义 SLI、benchmark 环境、workload 分层和 CI 回归预算；Phase 2 基于连续基线数据收敛为正式 SLO。

### Phase 1 输出

| 输出项 | 说明 |
|--------|------|
| **SLI 定义** | 延迟（物化耗时、级联传播延迟）+ 吞吐（因子数/秒） |
| **基准数据集** | 标准化 workload（小/中/大） |
| **Benchmark 环境** | 固定硬件配置，可复现 |
| **CI 回归阈值** | 相对阈值，非绝对秒数 |

### CI 性能门禁

| 阈值 | 行为 |
|------|------|
| **退化 > 15%** | 告警（WARNING） |
| **退化 > 25%** | 阻断（ERROR） |

### Phase 2 输出

- 正式 P50/P95/P99 延迟目标
- 吞吐量目标（因子数/秒）
- 容量规划基准

---

## SLI 指标集

### 决策

**D-2**: Phase 1 的性能 SLI 聚焦端到端延迟与吞吐；资源利用率仅作为 saturation/diagnostic 指标，不纳入 SLI 承诺。编译耗时作为次级延迟指标保留观测，但不作为首批核心 SLI。

### SLI 优先级

| 优先级 | 指标类型 | 具体指标 | 说明 |
|--------|---------|---------|------|
| **P0** | 端到端延迟 | 物化完成延迟（trigger → materialize_done） | 未来正式 SLO 的核心指标 |
| **P0** | 端到端延迟 | 级联传播延迟（invalidation_enqueued → downstream_done） | 异步级联场景关键指标 |
| **P1** | 吞吐 | entities/s、rows/s | 容量规划和回归对比 |
| **P2** | 子阶段延迟 | 编译耗时、读取耗时、执行耗时、写出耗时 | 控制面/冷路径性能 |
| **支持性** | 资源 | 内存峰值、CPU、队列 backlog age | 诊断指标，不作为 SLI |

### 延迟指标分层

```
业务主延迟（P0 SLI）
├── 物化完成延迟: trigger → materialize_done
└── 级联传播延迟: invalidation_enqueued → downstream_done

内部子阶段延迟（P2 诊断）
├── 编译耗时
├── 读取耗时
├── 执行耗时
└── 写出耗时
```

---

## 基准测试框架

### Workload 分层

| 规模 | 数据量 | 标的数 | 天数 | slot 倍数 | 用途 |
|------|--------|--------|------|-----------|------|
| **S** | 10K rows | 10 | 100 | 10 | 快速回归 |
| **M** | 500K rows | 100 | 500 | 10 | 标准基准 |
| **L** | 5M rows | 500 | 1000 | 10 | 压力测试 |

### Benchmark 环境

- 固定硬件配置（CPU、内存、磁盘）
- 隔离环境，避免干扰
- 可复现的数据集

### 2026-03-14 v1 基准实现

**D-3**: Phase 6 的首版 benchmark harness 固化为 [`scripts/benchmarks/derived_benchmark.py`](../../../../../../../scripts/benchmarks/derived_benchmark.py)，覆盖 `query / materialize / shadow_compare` 三类 workload。定时窗口只覆盖 workload 执行本身，不把 synthetic fixture 构造时间纳入 latency，避免把数据生成噪音混入回归预算。

### 本地基线快照（2026-03-14）

以下结果来自 2026 年 3 月 14 日在本地开发环境执行：

```bash
uv run --no-sync python scripts/benchmarks/derived_benchmark.py --scale S --scale M --iterations 3
uv run --no-sync python scripts/benchmarks/derived_benchmark.py --scale L --iterations 1
```

| Workload | Scale | Elapsed (s) | Throughput (rows/s) | 用途 |
|----------|-------|-------------|---------------------|------|
| `query` | `S` | `0.001238` | `8.08M` | 观测 |
| `query` | `M` | `0.001238` | `403.78M` | 观测 |
| `query` | `L` | `0.005208` | `960.02M` | 夜间 / 手工观测 |
| `materialize` | `S` | `0.001602` | `6.24M` | PR 阻断 |
| `materialize` | `M` | `0.027121` | `18.44M` | PR 阻断 |
| `materialize` | `L` | `0.368278` | `13.58M` | 夜间 / 手工观测 |
| `shadow_compare` | `S` | `0.003378` | `2.96M` | PR 阻断 |
| `shadow_compare` | `M` | `0.060801` | `8.22M` | PR 阻断 |
| `shadow_compare` | `L` | `0.810838` | `6.17M` | 夜间 / 手工观测 |

说明：

- `query` 当前仍保留为观测指标，不纳入 Phase 1 的 PR 阻断。原因是本地微基准已经进入毫秒级，容易被调度与缓存抖动放大噪音。
- `materialize` 与 `shadow_compare` 直接对应当前 v1 主链的冷路径成本，因此进入首批 regression budget 门禁。
- `L` 规模用于压力与容量感知，先放入夜间或手工执行，不纳入日常 PR gate。

---

## 监控集成

与现有监控系统集成（参考 ADR-018）：

| 指标 | 现有监控 | 扩展需求 |
|------|---------|---------|
| 物化耗时 | Histogram ✅ | 需补充端到端时间戳 |
| P50/P95/P99 | 仪表盘 ✅ | 需关联 CI 基准 |
| 慢物化告警 | MaterializationSlow ✅ | 需增加级联传播告警 |

---

## CI 回归检测

### 流程

```
1. PR 提交 → 触发性能测试
2. 运行 benchmark（S/M 规模）
3. 对比基线
   ├── 退化 < 15%: 通过
   ├── 退化 15-25%: WARNING，允许合并但需 review
   └── 退化 > 25%: 阻断
4. 更新基线（main 分支合并后）
```

### 首批门禁矩阵

**D-4**: Phase 1 v1 的 benchmark gate 采用“PR 阻断 + 夜间观测”双层策略。

| Workload | S | M | L |
|----------|---|---|---|
| `query` | WARNING only | WARNING only | Observe only |
| `materialize` | ERROR on >25% / WARNING on >15% | ERROR on >25% / WARNING on >15% | Observe only |
| `shadow_compare` | ERROR on >25% / WARNING on >15% | ERROR on >25% / WARNING on >15% | Observe only |

### 基线管理

- 基线存储：Git LFS 或专用存储
- 更新频率：每周或每个 release
- 回滚机制：保留历史基线

---

## 反例：什么不适合放入本 ADR

- ❌ 具体的硬件配置（属于部署文档）
- ❌ 单个算子的性能优化（属于算子实现）
- ❌ 容量规划具体数值（Phase 2 基于 SLO 推导）

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| **ADR-018: Monitoring & Alerting** | 现有监控基础设施 |
| **ADR-019: Testing Strategy** | CI 测试框架集成 |
| **ADR-035: Invalidation Cascade** | 级联传播延迟的定义基础 |

---

## 决策记录

| 日期 | 决策 |
|------|------|
| 2026-03-12 | D-1: Phase 1 定义测量框架 + CI 回归预算，Phase 2 收敛正式 SLO |
| 2026-03-12 | D-2: SLI 聚焦端到端延迟 + 吞吐，资源作为诊断指标 |
| 2026-03-14 | D-3: 基准 harness 固化为 `query / materialize / shadow_compare` 三类 workload，定时窗口排除 synthetic fixture 构造 |
| 2026-03-14 | D-4: PR gate 只阻断 `materialize` 与 `shadow_compare` 的 S/M 回归；`query` 与全部 L workload 先做观测 |
