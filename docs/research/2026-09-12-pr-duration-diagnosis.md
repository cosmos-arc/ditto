# PR 验证时长诊断：排队与执行分解

- 日期：2026-09-12。数据：最近 15 个 `pull_request` 触发的 CI 成功 runs（含 jobs 时间戳），经 GitHub Actions API 只读采集（#134）。
- 结论先行：**超时几乎全部来自执行而非排队**。真实排队中位数约 3 秒（`min(job.started_at) − run.created_at`）；全程 ≈ 执行窗口。要接近 ADR 0011 的 10–15 分钟目标，杠杆是压缩 backend 分片关键路径或并行化后置阶段，而不是治理排队或 runner 额度。

## 数据（全程 = run created→updated）

| 分组 | n | 全程中位数 | 排队中位数 | 执行中位数 |
|---|---|---|---|---|
| full 门（24–28 jobs：根/工具链/契约类变更） | 11 | 16.4 min | ~0.05 min | 16.4 min |
| 部分（docs 类 7–9 jobs） | 4 | 0.4 min | ~0.05 min | 0.3 min |

full 组代表样本：#124 17.7m、#126 16.9m、#125 16.8m、#128 16.4m、#110 16.4m、
#135（三 run）16.2–28.3m（28.3m 为第二次 attempt 含重跑失败 job）、#137 16.0m、
#109 34.6m（分片前的 backend coverage 33.6m）。最慢 job：backend-shards (0) 14.3m、
(1) 14.0m；随后 OpenAPI compat、Platform smoke 等后置阶段串行叠加。

## 归因与口径说明

1. **排队可忽略**：public 仓库 runner 供给充足，`min(job.started_at)−created_at` 中位数 ~3 秒。
   注意不能用 `max(job.started_at)` 当排队——流水线后置 job（OpenAPI/Platform smoke）在
   自身排队于 `needs` 依赖时 started_at 晚至 run 末尾，那是执行内的阶段依赖。
2. **关键路径 = backend 分片 + 串行后置**：#109 之后 backend coverage 已分片（33.6m →
   ~14m/片），但分片仍是关键路径；其后置阶段继续串行。
3. **分类保守度未见证据性问题**：本窗口的 full 门 PR 全部因触碰根/工具链/契约/lock
   文件而正确进入全量（#110/#124–128/#135/#137 皆属此类）；docs 类 0.4 分钟说明普通
   文档路径已足够轻。**局限**：窗口内没有纯 Web/纯后端功能 PR 样本，这两类的实际时长
   未经测量（分类行为由 `test_ci.py` 固定：纯 Web 不含 backend 分片，普通后端不含
   web-prototype）。
4. **concurrency cancel-in-progress** 对时长无实质收益（无排队积压），仅快速连推时节约额度。
5. 16.4m 略超 15m 上限的部分≈后置阶段串行叠加；属于全量门的固有余量，未发现
   误分类导致的浪费。

## 建议的后续杠杆（不在 #134 范围，仅登记）

- 压缩 backend 分片时长（测试级重新分配，参照 toolchain.md 已有的分片耗时记录）；
- 评估后置阶段（api-contract、platform-smoke）与 backend 分片并行的可行性
  （需核对制品依赖方向，不能为并行弱化「构建先于消费」）；
- 两者都以普通 Web/后端 PR 的实测样本为前提（本诊断的已知盲区）。
