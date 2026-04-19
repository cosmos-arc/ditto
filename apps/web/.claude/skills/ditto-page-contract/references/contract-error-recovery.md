# Contract Error Recovery — 验证失败修复指引

> 对应 validator 13 项检查的逐条修复指引。每次 --validate 失败时参考此表。

---

| # | 检查项 | 失败时修复步骤 |
|---|--------|---------------|
| 1 | JSON Schema | 读 schema 错误提示，补缺字段或修正类型。常见：`createdAt`/`updatedAt` 格式应为 `YYYY-MM-DD` |
| 2 | Prototype 文件 | 确认 `prototypeRef` 路径正确，文件在 `docs/designs/specs/prototypes/` 下且非空 |
| 3 | Blueprint refs | 确认 `blueprintRefs` 中的文件存在于 `docs/designs/specs/`（去掉 `#anchor` 后检查） |
| 4 | prototypeSelector | 重新运行 `create.mjs --prototype <path>` 查看探测结果，或手动从 HTML 中找对应选择器 |
| 5 | reactSelector 格式 | 修正为 `[data-slot='xxx']` 或 `[data-testid='xxx']`，检查引号和方括号 |
| 6 | metrics baseline | 运行 `--refresh-metrics <page>` 重新捕获 |
| 7 | universal states | 补全 `["loading", "empty", "error", "stale"]` 到 `states.universal` |
| 8 | 零容忍阈值 | 将 `consoleErrors`/`pageErrors`/`missingSelectors`/`targetMismatch` 全部设为 `0` |
| 9 | shellFamily | 对照 spec §10 修正，有效值：`command-center`/`analytical`/`catalog`/`object-hub`/`studio`/`ops-console`/`radar` |
| 10 | pagePattern | 对照 spec §11 修正，有效值：`global-command-center`/`analytical-overview`/`catalog-screener`/`object-hub`/`studio-builder`/`queue-ops-console`/`ledger-execution-console`/`config-integration-console` |
| 11 | subSlots selector | 同 #4/#5，修正 prototypeSelector 和 reactSelector 格式 |
| 12 | generated artifacts | 运行 `bun run generate-contracts` 重新生成，确认输出无语法错误 |
| 13 | status gate | `draft` 是 WARNING 不阻断；`unknown` 是 BLOCK → 检查 status 值是否为 `draft`/`contract-ready`/`verified`/`deprecated` |

### V2 新增检查

| # | 检查项 | 级别 | 失败时修复步骤 |
|---|--------|------|---------------|
| 14 | a11y role | WARN | 为 required slot 添加 `a11yRole`（如 rail→`"navigation"`, main→`"main"`, sidebar→`"complementary"`） |
| 15 | responsive | WARN | 如果 viewports 含 compact 且 slot 在 compact 下有行为变化，添加 `responsiveBehavior: { compact: "hidden"\|"collapsed"\|"overlay"\|"reflow" }` |
