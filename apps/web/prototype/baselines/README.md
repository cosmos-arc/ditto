# 原型历史冻结记录

`frontend-recovery-m0-2026-09-04.json` 是迁移前 `.frozen-baseline.json` 的原始字节，
绑定其中的 `baselineCommit` 与旧路径；它用于恢复历史身份，不证明当前源码。
其 screenshotRef 是当次捕获位置，不能据此声称本 checkout 含有截图副本。

当前冻结记录在上级 `.frozen-baseline.json`，由
`bun scripts/capture-prototype-baseline.mjs` 在已提交原型源码上真实捕获。
`bun run audit:prototype-freeze` 检查当前记录。路径迁移不能通过手工更改旧记录的
SHA-256 或 capturedAt 来冒充重新测量。
