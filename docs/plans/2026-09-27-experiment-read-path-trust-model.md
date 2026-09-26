# perf(analysis): 实验读路径信任模型——hash 已验证行的快速读路径

> 状态：已实施（#312，2026-09-27）。采用内容寻址验证缓存（方案 B 的内容级形态）：
> key 覆盖行内全部验证输入列，命中即复用已验证冻结对象，任何漂移换 key 全量重验证。
> 未采用方案 A（跳过读侧验证）——防御深度保留。

## 背景

`test_128_candidates_survive_restart_without_duplicate_claims[4]`（capacity 慢车道，CI ~213s）
profiling 结论：耗时不在磁盘 fsync，而在读路径的重复全量验证。已在 ea578a69（branch
`perf/capacity-read-path`）完成两项无损优化（46s→29s 本地，-37%）：

- `ContentHash.__post_init__` 逐字符 hex 校验改 regex fullmatch（原 2.4 亿次生成器步进）；
- `CandidateSpec.parameter_hash` 实例级 memo（原每次访问 json.dumps+sha256，95.5 万次）。

## 剩余热点（本票范围）

读侧对**字节级 hash 已验证的行**仍做全量 Python spec 验证：

1. `_json_value`（persistence.py:99）：每次 `canonical_payload()` 重新走整棵树验证
   JSON 兼容性——读侧 1006 万次调用；`CanonicalPayload.__post_init__` 还会对刚算出的
   bytes 再 sha256 一次（写读双重哈希）。
2. `validate_promotion_objective_graph`：launch spec 每次读取重跑，`_copy_trial` 深拷贝
   全部 128 个 trial（79.7 万次）。
3. `_fold_view`/`_attempt_view`：每 tick 全量重建视图，`reader.py:359` 的 sha256 校验
   通过后，spec 构造内部又重新 canonical 化同一内容。

## 候选方案（需裁决取舍）

- A. hash 已验证行的快速读路径：写时全量验证一次，读时信任 `fold_spec_json` 等字节
  hash 比对结果，跳过树级重验证。收益全局（所有集成测试与真实查询），代价是读侧
  防御深度降一层。
- B. 实例级 memo 验证结论（同 `parameter_hash` 模式推广）：保持验证语义，只消除
  同实例重复计算。收益中等，无语义变化。
- C. 读侧构造入口传"已验证"标记，仅跳过同一函数内紧邻的双重哈希（最小改动）。

## 边界

- 账本一致性相关的失败模式（hash 不匹配、结构损坏）仍必须 fail closed；
- PIT/cutoff 语义不受影响（本票只动验证时序，不动数据语义）；
- 验收：capacity 测试 CI 时长、`packages/analysis` + `packages/application` 集成套件
  全绿，读侧损坏行注入测试仍拦截。

## 关联

- #225（CI 慢因谱系）、#226（串行 lane，挂起）
- branch `perf/capacity-read-path`（已完成的两项优化，先行合入）
