# ADR: Research Artifact Manifest & Index 策略

> 日期：2026-05-18
> 状态：Proposed（Batch 5 A-3，不强制实现）
> 范围：`ditto_analysis.research.artifact_service` + `ditto_analysis.research.catalog_service`

## 背景

当前 `ResearchArtifactService` 提供：
- 产物文件 I/O（parquet/csv/feather/JSON）
- 基于文件 glob 的 artifact 路径解析（`resolve_artifact_relative_path`）
- 基于文件系统 mtime 的元数据读取（`read_source_snapshot_ids`）

缺失的能力：
- **Manifest 验证**：`manifest_hash` 字段存在于 snapshot record 中，但无计算或校验逻辑
- **Index 查询**：无法按 derived_id/version/时间范围 高效查询产物列表
- **Lineage 追溯**：无法从 snapshot 反向追溯其输入产物的完整性

## 决策

### 短期（当前不实现）

不强制引入 manifest 计算或 index 结构。理由：
1. 当前 research snapshot 数量级小（<100），文件 glob 足够
2. manifest_hash 作为 opaque string 已经正确持久化，校验逻辑可在需要时添加
3. 过早产品化研究 artifact 会增加变更阻力

### 中期演进方向

当以下任一条件触发时，应重新评估并实现：

1. **产物数量超过 1000** → 引入 SQLite-backed index
2. **需要跨 snapshot 数据一致性校验** → 实现 manifest hash 计算（SHA-256 of parquet metadata）
3. **需要产物血缘查询** → 在 `ResearchCatalogService` 增加 lineage 表

建议的演进路径：

```
Phase 0 (当前):
  artifact_service = 文件 I/O + glob 解析
  manifest_hash = opaque string

Phase 1 (按需):
  manifest computation = SHA-256(parquet metadata bytes)
  index = SQLite table (artifact_id, derived_id, version, path, hash, created_at)
  catalog_service.query_artifacts(derived_id, version_range)

Phase 2 (可选):
  lineage = input_snapshot_ids → output_snapshot_id DAG
  verification = on-read manifest check
```

### 约束

- `ResearchArtifactService` 不应依赖 `ResearchCatalogService`（保持单向依赖）
- manifest 计算逻辑应独立为 `ManifestComputer` 纯函数模块
- index 查询应通过 Protocol 解耦，支持内存/SQLite/未来外部 catalog

## 不做的事

- 不在 Batch 5 实现 manifest 计算或 index
- 不引入新的数据库表或文件格式
- 不改变现有 `ResearchArtifactService` 公共 API

## 参考

- `packages/analysis/src/ditto_analysis/research/artifact_service.py` — 当前实现
- `packages/analysis/src/ditto_analysis/research/domain.py` — manifest_hash 字段定义
- `packages/analysis/src/ditto_analysis/research/catalog_service.py` — catalog 元数据管理
