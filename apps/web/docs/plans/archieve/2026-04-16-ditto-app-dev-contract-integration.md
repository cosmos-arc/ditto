# ditto-app-dev 合同集成调整

> **版本**：v1.0
> **日期**：2026-04-16
> **上游**：2026-04-16-ditto-page-contract-design（POC 已完成）
> **目标**：调整 ditto-app-dev 命令，使其消费新的页面合同系统

---

## 1. 调整范围

`ditto-app-dev` 命令通过自然语言指令指导 AI 操作，不直接导入代码模块。
调整集中在 **`.claude/commands/ditto-app-dev.md`** 的指令文本更新。

### 受影响 Phase

| Phase | 变更类型 | 说明 |
|-------|---------|------|
| 10 METRIC | 行为变更 | contract 有 baseline → 跳过 Playwright 提取 |
| 11 ARCHITECT | 输入扩展 | 新增 subSlots、interactions、metrics.baseline 布局策略 |
| 12 IMPLEMENT | 输入扩展 | requiredStates 从 contract JSON 读取，新增 subSlots 验证 |
| 14 VERIFY | 输入替换 | selector/threshold 从 contract JSON 读取，不再从 visual-audit.config.mjs |
| 15 SHIP | 前置条件 | 检查 contract.status === "contract-ready" |

### 不受影响

- Phase 13 POLISH（交互打磨不依赖合同数据）
- 迭代协议（--iterate 模式逻辑不变）
- 原型缺陷处理协议（不变）
- Agent 分工与 Model Routing（不变）

---

## 2. Phase 10: METRIC 调整

### 当前行为

每次启动 Playwright 提取 prototype 度量 → 推导布局策略 → 写入 page contract。

### 调整后行为

```
Phase 10 启动
│
├─ 检查 docs/contracts/pages/<page>.contract.json 是否存在？
│   ├─ 否 → 提示用户先运行 /ditto-page-contract --create <page>
│   │        或使用 --force-metric 强制执行度量提取
│   └─ 是 → 检查 metrics.baseline 是否非空？
│       ├─ 非空 → 直接读取 baseline，输出度量摘要，跳到 Phase 11
│       └─ 空 → 回退到 Playwright 提取流程（与当前行为一致）
│
├─ --force-metric 参数 → 无论 baseline 是否存在，强制启动 Playwright 提取
│   提取完成后更新 contract JSON 的 metrics 字段，version 递增
│
└─ PROTOTYPE_NORMALIZE_CSS 来源更新
    从 visual-audit.config.mjs → visual-audit.config.generated.mjs
```

### Agent 描述更新

```
| 10 METRIC | Metric Reader | sonnet | 读取 contract.metrics.baseline（已有则跳过提取） | 无 |
```

### 新增参数

| 参数 | 说明 |
|------|------|
| `--force-metric` | 强制启动 Playwright 重放度量提取，忽略已有 baseline |

### 需要修改的指令段落

1. **输入参数表**（~L50-64）：新增 `--force-metric` 参数说明
2. **Agent 分工表**（~L72-79）：Phase 10 Agent 描述
3. **完整执行流**（~L97-130）：Phase 10 描述更新
4. **Phase 10 详细步骤**（~L150-197）：整个段落重写
5. **规范参考**（~L15-21）：`PROTOTYPE_NORMALIZE_CSS` 来源更新

---

## 3. Phase 11: ARCHITECT 调整

### 当前行为

从 `page-contracts.ts` 读取 slots/states/pattern，设计组件树。

### 调整后行为

输入源从 TypeScript 模块改为 contract JSON，新增以下信息维度：

| 新增字段 | 用途 |
|---------|------|
| `subSlots[]` | 页面级内容区块（如 main 下的 decision-banner），Phase 11 能看到更细粒度的结构 |
| `metrics.baseline` | 每个区域的布局策略（content-driven/fixed-width/flex），直接从合同读取，不再需要 Phase 10 推导 |
| `interactions[]` | 交互契约（如 sidebar-collapse），纳入状态管理策略 |
| `slots[].threshold` | 每个 slot 的验证阈值，Phase 11 可据此判断哪些区域需要更精确的布局实现 |

### Phase 11 输入更新

```
当前：
  Phase 10 度量数据 + page contract（slots/states/pattern）+ 现有组件库

调整后：
  contract JSON（slots/subSlots/states/metrics.baseline/interactions/thresholds）+ 现有组件库
```

### 需要修改的指令段落

1. **Phase 11 详细步骤**（~L200-246）：输入源、步骤 1（DOM 映射使用 subSlots）、步骤 4（状态管理纳入 interactions）

---

## 4. Phase 12: IMPLEMENT 调整

### 当前行为

从 page contract 读 `requiredStates` 实现 UI 状态，验证 `data-slot` 与 `requiredSlots` 匹配。

### 调整后行为

| 项目 | 当前 | 调整后 |
|------|------|--------|
| requiredStates 来源 | page-contracts.ts | contract JSON `states.universal` + `states.pageSpecific` |
| requiredSlots 来源 | page-contracts.ts | contract JSON `slots[]`（required=true） |
| data-slot 验证 | 仅验证 shell slot | 同时验证 `subSlots[].reactSelector` |
| 交互实现 | 无明确要求 | 实现 contract 中定义的 `interactions[]` |

### 需要修改的指令段落

1. **Phase 12 详细步骤**（~L250-295）：步骤 4（状态覆盖从 contract 读取）、步骤 5（Slot 一致性新增 subSlots 验证）

---

## 5. Phase 14: VERIFY 调整

### 当前行为

L2 从 `visual-audit.config.mjs` 读 selector 做对比，阈值硬编码 3%/5%。

### 调整后行为

| 项目 | 当前 | 调整后 |
|------|------|--------|
| L2 selector 来源 | visual-audit.config.mjs `VISUAL_AUDIT_PAGES` | contract JSON `slots[].prototypeSelector/reactSelector` + `subSlots[]` |
| L2 验证阈值 | 硬编码 3%/5% | contract JSON `slots[].threshold` / `subSlots[].threshold` |
| L3 像素阈值 | 硬编码 0.02 | contract JSON `visualThresholds.pixelDiffRatio` |
| 0 容忍项 | 无明确检查 | contract JSON `visualThresholds.consoleErrors/pageErrors/missingSelectors/targetMismatch` |
| NORMALIZE_CSS 来源 | visual-audit.config.mjs | visual-audit.config.generated.mjs |

### 需要修改的指令段落

1. **Phase 14 详细步骤**（~L354-422）：步骤 2（L2 selector/threshold 来源更新）、步骤 3（L3 阈值来源更新）、新增步骤 0（0 容忍项预检）

---

## 6. Phase 15: SHIP 调整

### 当前行为

手动推进 edition manifest 状态。

### 调整后行为

新增前置条件：`contract.status === "contract-ready"`。

```
Phase 15 启动
│
├─ 检查 contract JSON status
│   ├─ "contract-ready" → 继续执行
│   └─ "draft" → STOP，提示用户先运行 /ditto-page-contract --promote <page>
│
└─ 其余行为不变
```

### 需要修改的指令段落

1. **Phase 15 详细步骤**（~L425-447）：新增前置条件检查

---

## 7. 衔接流程更新

### 当前流程

```
ditto-design-cycle done → ditto-app-dev --implement → ditto-app-dev --ship
```

### 调整后流程

```
ditto-design-cycle done
    │
    ▼
ditto-page-contract --create <page>      ← 新增
    │  产出: docs/contracts/pages/<page>.contract.json (status: draft)
    │  自动生成: .generated.ts + .generated.mjs
    │
    ▼
ditto-page-contract --validate <page>    ← 新增
    │  10 项 BLOCK 检查
    │
    ▼
ditto-page-contract --promote <page>     ← 新增
    │  status: draft → contract-ready
    │  重新生成 .generated.ts + .generated.mjs
    │
    ▼
ditto-app-dev --implement <page>
    │  Phase 10: 读取 contract JSON → 跳过 Playwright（baseline 已有）
    │  Phase 11: 读取 contract slots/subSlots/states/metrics/interactions
    │  Phase 12: 从 contract 读取 states + 验证 subSlots
    │  Phase 14: 从 contract 读取 selector + threshold → 精确验证
    │  Phase 15: 检查 contract.status === "contract-ready"
    │
    ▼
完成
```

### 需要修改的指令段落

1. **与 ditto-design-cycle 的衔接**（~L542-564）：插入 ditto-page-contract 步骤
2. **规范参考**（~L15-21）：新增 ditto-page-contract 链接

---

## 8. 实施清单

### 文件变更

| 文件 | 变更 |
|------|------|
| `.claude/commands/ditto-app-dev.md` | 更新 5 个 Phase + 衔接流程 + 参数表 + 规范参考 |

### 逐段修改清单

- [ ] 规范参考区：新增 ditto-page-contract 链接，更新 page-contracts 链接
- [ ] 输入参数表：新增 `--force-metric`
- [ ] Agent 分工表：Phase 10 描述更新
- [ ] 完整执行流：Phase 10 描述更新
- [ ] Phase 10 详细步骤：重写为"读取优先"模式
- [ ] Phase 11 详细步骤：输入源更新，新增 subSlots/interactions
- [ ] Phase 12 详细步骤：requiredStates/subSlots 来源更新
- [ ] Phase 14 详细步骤：selector/threshold 来源更新
- [ ] Phase 15 详细步骤：新增 contract-ready 前置检查
- [ ] 衔接流程：插入 ditto-page-contract 步骤

### 不变部分

- Phase 13 POLISH（交互打磨不依赖合同数据）
- 迭代协议（--iterate 逻辑不变）
- 原型缺陷处理协议
- 禁止事项表
