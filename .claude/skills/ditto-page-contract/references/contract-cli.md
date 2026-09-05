# Contract CLI 命令参考

> ditto-page-contract 子命令的具体执行命令。

---

## --validate `<page>`

```bash
bun -e "
import { validateContract } from './.agents/skills/ditto-page-contract/scripts/validators/contract-validator.mjs';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const c = JSON.parse(await readFile(resolve('docs/contracts/pages/<PAGE>.contract.json'), 'utf-8'));
const r = await validateContract(c, { root: process.cwd() });
console.log(r.summary);
for (const ck of r.checks) console.log(ck.pass ? 'PASS' : 'FAIL', '|', ck.level, '|', ck.message);
"
```

## --validate --all

```bash
bun -e "
import { validateAllContracts } from './.agents/skills/ditto-page-contract/scripts/validators/contract-validator.mjs';
const r = await validateAllContracts({ root: process.cwd(), contractsDir: 'docs/contracts/pages' });
for (const p of r.results) console.log(p.id, p.passed ? 'PASS' : 'FAIL');
console.log('All passed:', r.allPassed);
"
```

## --promote `<page>`

```bash
# 1. 运行 --validate 确认全绿
# 2. 检查 edition-manifest status
# 3. Playwright 检查 prototype 无 console errors
# 4. 修改合同 JSON: status → "contract-ready", updatedAt → today
# 5. bun run generate-contracts
```

## --promote --all

```bash
# 1. 运行 validateAllContracts() → 全绿才继续
# 2. 遍历所有 status === "draft" 的合同
# 3. 对每个合同执行 promote 流程（manifest + console errors）
# 4. 输出批量提升报告
# 5. 任一失败 → 跳过该合同，继续其余
```

## --refresh-metrics `<page>`

```bash
bun .agents/skills/ditto-page-contract/scripts/create.mjs --prototype <prototype-path>
# 从输出中提取 metrics → 更新合同 JSON metrics 字段
# version++, updatedAt = today
# bun run generate-contracts
```

## --update `<page>`

```bash
# 读取当前合同 → 应用变更 → validate → 全绿才写入
# 允许更新: selector, threshold, subSlot, a11yRole, a11yLabel, responsiveBehavior
# 禁止更新: id, status, route, shellFamily, pagePattern（需要重新 --create）
# version++, updatedAt = today → bun run generate-contracts
```

## --create `<page>`

```bash
bun .agents/skills/ditto-page-contract/scripts/create.mjs --prototype <prototype-path>
# 输出包含: DOM 探测结果 + 度量 baseline
# AI 用这些输出完成 Phase S/T/W（详见 contract-create-phases.md）
```
