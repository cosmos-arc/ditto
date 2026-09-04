# Discovery Manifest 格式

## 文件路径

`.discovery-manifest.json`（项目根目录）

## Schema (v2)

```jsonc
{
  "version": 2,
  "status": "in-progress",
  "topic": "A 股多因子策略回测平台",
  "startedAt": "2026-04-17T10:00:00Z",
  "completedAt": null,
  "phases": {
    "1": { "name": "VISION", "status": "done", "completedAt": "..." },
    "2": { "name": "LANDSCAPE", "status": "in-progress" },
    "3": { "name": "SYSTEM", "status": "pending" },
    "4": { "name": "CONSTRAINTS", "status": "pending" },
    "5": { "name": "SYNTHESIS", "status": "pending" }
  },
  "artifacts": {
    "brief": "docs/brief/product-brief.md",
    "constitution": "docs/brief/constitution.md",
    "systemDescription": "docs/brief/system-description.md",
    "assumptions": "docs/brief/assumptions.md",
    "competitiveLandscape": "docs/research/competitive/landscape.md",
    "knowledgeGaps": "docs/research/domain/knowledge-gaps.md"
  }
}
```

**向后兼容**: 加载 v1 manifest 时，缺失字段用默认值初始化。

## 更新时机

每个 Phase 完成并通过 Phase Gate 后，统一更新 manifest：
- 对应 phase 的 status → "done"，completedAt → ISO timestamp
- 如有新文件产出，更新 artifacts 路径
- 不在提问过程中实时维护 manifest
