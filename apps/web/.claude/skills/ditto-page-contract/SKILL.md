---
name: ditto-page-contract
description: >
  页面合同管理 — 创建/验证/提升/更新合同。回答"这个页面如果要落到 React，什么叫对版？"
---

# /ditto-page-contract

管理 Ditto 页面合同（Page Contract）。

```
blueprint-approved → --create → draft → --validate → --promote → contract-ready → app-dev 消费
                                                                          ↑
                                                              --update（下游反馈）
```

---

## 输入

`$ARGUMENTS` — 命令 + 页面名

```bash
/ditto-page-contract --create home              # 从原型+蓝图生成草稿合同
/ditto-page-contract --validate home            # 验证合同完整性
/ditto-page-contract --validate --all           # 验证所有合同
/ditto-page-contract --promote home             # 验证全绿 → contract-ready
/ditto-page-contract --promote --all            # 批量提升所有 draft 合同
/ditto-page-contract --update home              # 下游反馈更新（selector/threshold/subSlot）
/ditto-page-contract --refresh-metrics home     # 重放 Playwright 度量
```

---

## Reference 文件

| 文件 | 内容 |
|------|------|
| [contract-cli.md](references/contract-cli.md) | 各子命令的具体 CLI 命令 |
| [contract-create-phases.md](references/contract-create-phases.md) | `--create` 的 AI 执行 phases（R/B/P+S+M/S/T/W）详情 |
| [contract-error-recovery.md](references/contract-error-recovery.md) | 15 项验证检查的逐条修复指引 |

---

## --create `<page>`

7-phase 流程。Phase P+M 自动化（`create.mjs`），其余 AI 执行。

```
Phase R: RESOLVE       → 确认 manifest status，定位 blueprint/prototype/state spec
Phase B: BLUEPRINT     → 提取模块清单 + 状态清单 + 交互清单
Phase P+S+M: PROBE     → create.mjs 自动化：DOM 探测 + 度量捕获
Phase S: SELECTOR MAP  → blueprint 模块 → prototype/react selector + a11y + responsive
Phase T: THRESHOLD     → shell slot 严阈值(3%) / content subSlot 宽阈值(5-8%)
Phase W: WRITE         → 组装 JSON → generate.mjs → 产出 .generated.ts + .generated.mjs
```

详见 [contract-create-phases.md](references/contract-create-phases.md)。

**产出**：`docs/contracts/pages/<page>.contract.json`（status: draft）+ 创建报告

**前置条件**：edition-manifest 中页面 `status === "reviewed"` 或 `"done"`

---

## --validate `<page>` | --validate --all

运行 `validateContract()` / `validateAllContracts()`（详见 [contract-cli.md](references/contract-cli.md)）。

**15 项检查**（13 BLOCK + 2 WARN）：

| # | 级别 | 检查项 |
|---|:----:|--------|
| 1 | BLOCK | JSON Schema（ajv） |
| 2 | BLOCK | Prototype 文件存在且非空 |
| 3 | BLOCK | Blueprint refs 可解析 |
| 4 | BLOCK | Required slot 有 prototypeSelector |
| 5 | BLOCK | Required slot 有合法 reactSelector |
| 6 | BLOCK | metrics.baseline 非空且结构合法 |
| 7 | BLOCK | states.universal 含 loading/empty/error/stale |
| 8 | BLOCK | 零容忍阈值 = 0 |
| 9 | BLOCK | shellFamily 在枚举中 |
| 10 | BLOCK | pagePattern 在枚举中 |
| 11 | BLOCK | subSlots selector 格式合法 |
| 12 | BLOCK | generated artifacts 语法正确 |
| 13 | WARN | status 门禁（draft=WARNING, unknown=BLOCK） |
| 14 | WARN | Shell 级 required slot 有 a11yRole |
| 15 | WARN | compact viewport 下 slot 标注 responsiveBehavior |

修复指引见 [contract-error-recovery.md](references/contract-error-recovery.md)。

---

## --promote `<page>` | --promote --all

**前置**：`--validate` 全绿 + manifest status reviewed/done + prototype 无 console errors

**流程**：修改合同 `status: "draft" → "contract-ready"` → 重新 generate

`--promote --all` 遍历所有 draft 合同，任一失败跳过继续。

---

## --update `<page>`

从 app-dev 反馈中更新合同字段。

**允许更新**：selector, threshold, subSlot, a11yRole, a11yLabel, responsiveBehavior
**禁止更新**：id, status, route, shellFamily, pagePattern（需重新 `--create`）

**流程**：读取 → 应用变更 → validate 全绿 → version++ → 写入 → regenerate

---

## --refresh-metrics `<page>`

重跑 `create.mjs` 捕获新度量 → 更新 `metrics` → version++ → regenerate

---

## 合同示例

参考 `docs/contracts/pages/home.contract.json`（已创建的 home 页合同）。

完整 Schema 见 `scripts/schema/contract.schema.json`。

---

## 规范参考

| 文件 | 内容 |
|------|------|
| `docs/plans/2026-04-16-ditto-page-contract-design.md` | 系统设计文档 |
| `scripts/schema/contract.schema.json` | JSON Schema |
| `scripts/validators/contract-validator.mjs` | 验证器 |
| `scripts/generate.mjs` | 代码生成器 |
| `scripts/create.mjs` | 创建脚本（Playwright 自动化） |
| `scripts/templates/` | 阈值策略 / normalize CSS / shell 预设 |
