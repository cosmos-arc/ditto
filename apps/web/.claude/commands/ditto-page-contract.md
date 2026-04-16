---
name: ditto-page-contract
description: >
  页面合同管理 — 创建/验证/提升合同。回答"这个页面如果要落到 React，什么叫对版？"
disable-model-invocation: true
---

# /ditto-page-contract 命令

管理 Ditto 页面合同（Page Contract）。

## 合同生命周期

```
blueprint-approved → --create → draft → --validate → --promote → contract-ready → app-dev 消费
```

---

## 输入参数

`$ARGUMENTS` — 命令 + 页面名

```bash
/ditto-page-contract --create home              # 从原型+蓝图生成草稿合同
/ditto-page-contract --validate home            # 验证合同完整性（不改合同）
/ditto-page-contract --validate --all           # 验证所有合同
/ditto-page-contract --promote home             # 验证全绿 → status: contract-ready
/ditto-page-contract --refresh-metrics home     # 重放 Playwright 度量
```

---

## 规范参考

- **设计文档**: `docs/plans/2026-04-16-ditto-page-contract-design.md`
- **JSON Schema**: `scripts/contract-generator/schema/contract.schema.json`
- **验证器**: `scripts/contract-generator/validators/contract-validator.mjs`
- **生成器**: `scripts/contract-generator/generate.mjs`
- **创建脚本**: `scripts/contract-generator/create.mjs`

---

## --create `<page>`

### 执行流程

```
Phase R: RESOLVE
├─ 读取 edition-manifest.json → 确认 page.status === "reviewed"
├─ 如果不是 → STOP，报告错误
└─ 定位 blueprint section、prototype HTML、state spec

Phase B: BLUEPRINT EXTRACT
├─ 解析 blueprint 对应 section（如 02_core_page_blueprints.md）
├─ 提取：页面目标、主/辅工作面、核心区块列表
├─ 提取：Tab Content Sections
├─ 提取：Component × State Matrix → states
└─ 产出：模块清单 + 状态清单

Phase P+S+M: PROBE + SELECTOR MAP + METRIC CAPTURE（自动化）
├─ 运行: bun scripts/contract-generator/create.mjs --prototype <path>
├─ Playwright 打开 prototype HTML（channel: 'chromium'）
├─ 注入 PROTOTYPE_NORMALIZE_CSS
├─ 探测 #default-view 内 DOM 结构 → sections[]
├─ 提取布局度量 → metrics.baseline
└─ 产出：DOM 树摘要 + 度量数据

Phase S: SELECTOR MAP（AI 辅助）
├─ blueprint 模块 → prototype selector（DOM 匹配）
├─ blueprint 模块 → react selector（shell family 预设 merge）
├─ required slot 找不到 → WARNING
└─ 产出：slots[] + subSlots[]

Phase T: THRESHOLD POLICY
├─ shell slot → 严阈值（3%）
├─ content subSlot → 宽阈值（5-8%）
├─ consoleErrors/pageErrors/missingSelectors → 0 容忍
└─ 产出：visualThresholds + slot.threshold

Phase W: WRITE
├─ 组装 JSON → docs/contracts/pages/<page>.contract.json
├─ 运行: bun scripts/contract-generator/generate.mjs
└─ status: "draft"
```

### 产出物

- `docs/contracts/pages/<page>.contract.json` — 合同 JSON
- `docs/contracts/reports/<page>-contract-report.md` — 创建报告
- 触发 `generate.mjs` → 更新 `.generated.ts` + `.generated.mjs`

### 注意事项

- 如果 `docs/contracts/pages/<page>.contract.json` 已存在，提示用户确认覆盖
- prototype 文件必须存在于 `docs/designs/specs/prototypes/` 下
- shellFamily 必须在 `SHELL_FAMILIES` 枚举中

---

## --validate `<page>` | --validate --all

### 执行流程

```bash
# 验证单个页面
bun -e "
import { validateContract } from './scripts/contract-generator/validators/contract-validator.mjs';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const c = JSON.parse(await readFile(resolve('docs/contracts/pages/<PAGE>.contract.json'), 'utf-8'));
const r = await validateContract(c, { root: process.cwd() });
console.log(r.summary);
for (const ck of r.checks) console.log(ck.pass ? 'PASS' : 'FAIL', '|', ck.level, '|', ck.message);
"

# 验证所有页面
bun -e "
import { validateAllContracts } from './scripts/contract-generator/validators/contract-validator.mjs';
const r = await validateAllContracts({ root: process.cwd(), contractsDir: 'docs/contracts/pages' });
for (const p of r.results) console.log(p.id, p.passed ? 'PASS' : 'FAIL');
console.log('All passed:', r.allPassed);
"
```

### 检查项（10 项 BLOCK 级）

| # | 检查项 | 说明 |
|---|--------|------|
| 1 | JSON Schema 验证 | ajv 编译 schema |
| 2 | Prototype 文件存在且非空 | 文件系统检查 |
| 3 | Blueprint section 可解析 | 文件系统检查 |
| 4 | required slot 有 prototypeSelector | 格式检查 |
| 5 | required slot 有合法 reactSelector | `[data-slot='...']` 格式 |
| 6 | metrics.baseline 不为空 | 结构检查 |
| 7 | states.universal 包含 4 种通用状态 | 值检查 |
| 8 | visualThresholds 中 0 容忍项为 0 | 值检查 |
| 9 | shellFamily 在枚举中 | 枚举检查 |
| 10 | pagePattern 在枚举中 | 枚举检查 |

### 验证失败处理

- 任何 BLOCK 级检查失败 → 报告具体失败项 → 不修改合同
- 所有检查通过 → 输出 "Ready for --promote"

---

## --promote `<page>`

### 前置条件

```
✓ --validate 全部通过
✓ edition-manifest 中页面 status === "reviewed"
✓ prototype HTML 无 console errors（Playwright page.on('console')）
✓ metrics.baseline 已捕获
```

### 执行流程

1. 运行 `--validate` — 必须全绿
2. 读取 edition-manifest 确认页面状态
3. 用 Playwright 检查 prototype 无 console errors
4. 修改 `docs/contracts/pages/<page>.contract.json`:
   - `"status": "draft"` → `"status": "contract-ready"`
   - `"updatedAt": "<today>"`
5. 运行 `bun scripts/contract-generator/generate.mjs` 重新生成
6. 输出 "Contract promoted to contract-ready"

### 提升失败处理

- 验证不通过 → 报告失败项 → 不修改 status
- prototype 有 console errors → 报告 errors → 不修改 status

---

## --refresh-metrics `<page>`

### 执行流程

1. 运行 `bun scripts/contract-generator/create.mjs --prototype <path>`
2. 从输出中提取 metrics
3. 更新合同 JSON 的 `metrics` 字段
4. `version` 递增
5. `updatedAt` 设为今天
6. 运行 `bun scripts/contract-generator/generate.mjs`

---

## 合同 JSON 结构

```jsonc
{
  "id": "home",                    // 页面 ID
  "version": 1,                    // 版本号（--refresh-metrics 递增）
  "status": "draft",               // draft | contract-ready
  "route": "/",                    // 路由路径
  "pagePattern": "global-command-center",
  "shellFamily": "command-center",
  "prototypeRef": "docs/designs/specs/prototypes/page-home.html",
  "viewports": [...],
  "slots": [...],                  // Shell 级布局区域
  "subSlots": [...],               // 页面级内容区块
  "states": { "universal": [...], "pageSpecific": [...] },
  "flags": { "hasStatusBar": false, "sidebarCollapsible": true },
  "metrics": { "baseline": {...} },
  "visualThresholds": {...}
}
```

完整 Schema 见 `scripts/contract-generator/schema/contract.schema.json`。
