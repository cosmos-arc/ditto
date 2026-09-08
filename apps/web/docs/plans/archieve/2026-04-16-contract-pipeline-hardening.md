# Contract Pipeline Hardening — 反馈分析与执行计划

> **日期**: 2026-04-16
> **范围**: ditto-page-contract 流水线从 POC 到生产级门禁
> **输入**: 外部架构审查反馈 + 代码验证

---

## 1. 现状诊断

### 流水线分层（已验证合理）

```
ditto-product-arch → ditto-design-cycle → ditto-page-contract → ditto-app-dev → visual-audit / check
```

四层职责清晰：product-arch 定义"做什么"、design-cycle 产出"长什么样"、page-contract 定义"什么叫对版"、app-dev 兑现合同。

### 核心问题

**"有文档有 JSON 有 generator，但验证脚本没有真正检查浏览器 DOM，对版审计还没切到 generated config，check 也存在假绿风险。"**

流水线看起来完整，实际落地仍靠 agent 主观理解。质量不可重复、不可审计。

---

## 2. 已确认的技术问题（7 项）

### 2.1 generated mjs 语法错误 — Critical

**文件**: `scripts/visual-audit.config.generated.mjs:49-51, 60-62`
**根因**: `scripts/contract-generator/generate.mjs:258-259, 265-266`

```js
// 当前（错误）— key 未加引号
lines.push(`      ${key}: "${val}",`);

// 修复
lines.push(`      '${key}': "${val}",`);
```

`decision-banner`、`priority-queue` 等 kebab-case key 在 JS 中不是合法标识符，`node --check` 直接报 SyntaxError。

### 2.2 visual-audit.mjs 消费旧配置 — Critical

**文件**: `scripts/visual-audit.mjs:16`

```js
// 当前（错误）
import { ... } from "./visual-audit.config.mjs";

// 应改为
import { ... } from "./visual-audit.config.generated.mjs";
```

generated config 存在但未被消费。pipeline 断裂。

### 2.3 tsc --noEmit 假绿 — High

**文件**: `package.json:10`

```json
// 当前（假绿）
"check": "biome check . && tsc --noEmit && vitest run"

// 修复
"check": "biome check . && tsc -b && vitest run"
```

根 `tsconfig.json` 使用 `files: []` + `references`，`tsc --noEmit` 检查 0 个文件。应改 `tsc -b` 走 build mode 检查所有子项目。

### 2.4 create.mjs setContent 破坏加载上下文 — High

**文件**: `scripts/contract-generator/create.mjs:205-216`

```js
const html = await readFile(prototypePath, "utf-8");
await page.setContent(html, { waitUntil: "networkidle" });
```

`setContent` 将 base URL 设为 `about:blank`，所有相对路径（字体、CSS、图片）失效。度量数据可能不可靠。

**修复方案**: 改为启动本地 HTTP server，通过 `page.goto('http://localhost:PORT/...')` 加载。

### 2.5 validator 只检查 slots 不检查 subSlots — Medium

**文件**: `scripts/contract-generator/validators/contract-validator.mjs:143-159`

`checkPrototypeSelectorFormat` 只遍历 `contract.slots`，subSlots 的 selector 缺失不会被捕获。

### 2.6 draft 合同能通过全量验证 — Medium

**文件**: `contracts/pages/home.contract.json:4`

`"status": "draft"` 但 10 项检查无一涉及 status 字段。"验证通过" ≠ "可交付"。

### 2.7 合同失败不阻断 done — Medium

**文件**: `.claude/commands/ditto-design-cycle.md:781, 798`

```markdown
合同创建失败 → WARNING，记录原因，不阻断 done
验证失败 → 输出失败项，不阻断 done 流程
```

坏原型可流入实现阶段。

---

## 3. 反馈建议评估

### 3.1 采纳的建议

| 建议 | 理由 |
|------|------|
| Contract JSON 为唯一源头，generated 文件提交到 git | 已是当前策略，正确 |
| visual-audit.mjs 切到 generated config | 必须修，否则 pipeline 断裂 |
| check 脚本改掉假绿 | 必须修，否则门禁无意义 |
| create.mjs 改为 HTTP server | 必须修，否则度量不可靠 |
| contract-validator 增加 browser-backed 检查 | 方向正确，分两步走 |
| design-cycle 区分 exploration / acceptance | 方向正确，用 `--strict` 标志实现 |
| ditto-app-dev ship gate 扩展 | 方向正确，但 visual audit 不适合每次 ship 强制跑 |

### 3.2 需要调整的建议

**"generated 文件要么全部 gitignored，要么全部提交"**

当前策略（提交到 git）正确。原因：
- Contract JSON 是确定性派生 → 提交可审计
- gitignore 增加环境依赖
- CI 用 `git diff --exit-code` 检测漂移是好补充

**"7 个新 Agent Skills"**

YAGNI。当前核心问题是现有脚本有 bug，不是缺 skill。P0 不新增任何 skill，P1 最多考虑 `ditto-visual-parity-auditor`。

**"ditto-design-cycle 拆成两个命令"**

不拆命令。用 `--strict` 标志区分：
- `--create` = exploration（合同失败 warning）
- `--create --strict` = acceptance（合同失败阻断 done）

### 3.3 未采纳的建议

无。所有建议均有合理内核，只是优先级和实现方式需要调整。

---

## 4. 执行计划

### P0 — 修硬门禁

> 目标：让现有工具链真正能跑通、能报错、能阻断

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| 1 | 修 generate.mjs key quoting | `scripts/contract-generator/generate.mjs:258-259, 265-266` | `${key}` → `'${key}'` |
| 2 | visual-audit.mjs 切到 generated config | `scripts/visual-audit.mjs:16` | import 路径改为 `.generated.mjs` |
| 3 | check 脚本改掉假绿 | `package.json:10` | `tsc --noEmit` → `tsc -b` |
| 4 | validator 增加 subSlots selector 检查 | `contract-validator.mjs` | 新增 check #11 |
| 5 | validator 增加 generated artifact 语法检查 | `contract-validator.mjs` | 新增 check #12：`node --check` generated mjs |
| 6 | validator 增加 status 门禁 | `contract-validator.mjs` | draft 合同 `--validate` 输出 WARNING |
| 7 | design-cycle 加 `--strict` 模式 | `ditto-design-cycle.md` | strict 下合同失败阻断 done |

### P1 — 合同真正对版

> 目标：合同验证从"结构检查"升级为"浏览器真实检查"

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| 1 | create.mjs 改为 HTTP server | `scripts/contract-generator/create.mjs` | 启动本地 server，`page.goto()` 替代 `setContent` |
| 2 | validator 增加 Playwright selector 检查 | `contract-validator.mjs` | 打开 prototype，验证 prototypeSelector 存在 |
| 3 | validator 增加 console/page error 检查 | `contract-validator.mjs` | `page.on('console')` + `page.on('pageerror')` |
| 4 | validator 增加 metrics 阈值检查 | `contract-validator.mjs` | 重采 metrics，对比 contract baseline |
| 5 | visual audit 从报告型改为门禁型 | `scripts/visual-audit.mjs` | 超阈值 `process.exit(1)` |
| 6 | home contract promote 到 contract-ready | `contracts/pages/home.contract.json` | 跑完全流程后 promote |

### P2 — 规模化

> 目标：3 页闭环验证，为 21 页铺路

| # | 任务 | 说明 |
|---|------|------|
| 1 | 选 3 个不同 shellFamily 页面跑通闭环 | command-center + analytical + catalog |
| 2 | 清理旧 page-contracts.ts / 旧 visual config | 避免双源漂移 |
| 3 | CI 增加 `contracts:validate --all --strict` | PR 门禁 |

---

## 5. 变更分流规则

> 蓝图管"为什么和是什么"，原型管"长什么样和怎么动"，contract 管"什么叫对版"，实现只负责兑现合同。

| 变更类型 | 示例 | 处理方式 |
|---------|------|---------|
| 纯视觉调整 | 间距、字号、局部层级、密度 | 改 prototype → `--refresh-metrics` |
| 交互/状态调整 | 新增 tab、drawer、loading/empty 行为 | 回 blueprint/state spec → 重生成 prototype + contract |
| 技术约束 | 实现阶段发现的技术映射差异 | 记录 proto-deviation → 改 contract 或回蓝图 |
| 方向未变的迭代 | 原型不满意但信息结构不变 | `ditto-design-cycle --iterate` → `--refresh-metrics` |

---

## 6. 验证标准

P0 完成后必须满足：

- [ ] `node --check scripts/visual-audit.config.generated.mjs` exit 0
- [ ] `bun run check` 中 tsc 真正检查所有文件（非假绿）
- [ ] `bun scripts/contract-generator/validators/contract-validator.mjs` 覆盖 slots + subSlots + generated artifact + status
- [ ] `ditto-design-cycle --create --strict` 下合同失败阻断 done
- [ ] `bun scripts/contract-generator/generate.mjs` 输出的 mjs 语法正确

P1 完成后额外满足：

- [ ] `create.mjs` 通过 HTTP server 加载 prototype（非 setContent）
- [ ] validator 在真实浏览器中验证 selector 存在性 + console error
- [ ] visual audit 超阈值时 exit 1
- [ ] home.contract.json status = "contract-ready"
