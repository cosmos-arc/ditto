# Web 运行证据迁出记录

日期：2026-09-04

Monorepo 只保留必要的小型 canonical golden。重复 viewport 截图矩阵和浏览器
trace 属于运行制品，应由 CI artifact 按保留策略托管，而不应继续扩大 Git tree。

## 可恢复性

- 原始内容永久保留在导入提交 `3d2e44b5` 及其祖先历史中。
- 迁移工作站另存恢复包：
  `/Users/chevy/Desktop/code/ditto-monorepo-migration-20260904/tree-evidence-archive/redundant-web-evidence-20260904.tar.gz`
- 恢复包 SHA-256：
  `014e789037da846af3a90d48c7723c9424e7692a7ff4eacf909766f788fbb34f`
- 归档条目数：576。

## 迁出范围

- `apps/web/docs/review/r3-research-acceptance/live/trace.zip`
- `apps/web/docs/review/product-beta-20260830/visual-audit-1200/`
- `apps/web/docs/review/product-beta-20260830/visual-audit-1200-declared/`
- `apps/web/docs/review/product-beta-20260830/visual-audit-1200-declared-all/`
- `apps/web/docs/review/product-beta-20260830/visual-audit-1366/`
- `apps/web/docs/review/product-beta-20260830/visual-audit-1536-rerun/`
- `apps/web/docs/review/visual-audit-1200/`
- `apps/web/docs/review/visual-audit-1366/`
- `apps/web/docs/review/visual-audit-markets-1366/`

保留的 canonical 证据包括 product-beta 1536px 主矩阵、必要的内容寻址 JSON
manifest，以及单项不超过仓库 allowlist 的视觉 golden。后续 PR trace、coverage HTML、
大 payload 和重复截图只能上传 CI artifact：PR 保留 14 天，main/nightly 保留 30 天，
release evidence 随 release 长期保留。
