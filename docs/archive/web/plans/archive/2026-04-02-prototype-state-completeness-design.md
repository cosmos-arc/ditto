# 原型状态完整度设计方案

> **日期**：2026-04-02
> **状态**：Approved
> **范围**：ditto-design-cycle + ditto-product-arch 两个上游 skill 的改造

---

## 问题诊断

当前原型只生成"默认态"，缺失全部非 active 状态：

| 状态类别 | 业界标准 | 当前状态 |
|----------|---------|---------|
| 每个 tab 面板内容 | 全部渲染 | 仅 1/10 页面有 |
| Modal / Dialog / Sheet | 覆盖层展示 | 0 个 |
| Drawer / Slide-over | 侧拉面板展示 | 0 个 |
| Empty state | 空数据占位 | 仅 Home 有描述 |
| Loading / Skeleton | 加载骨架 | 0 个 |
| Error state | 错误/重试 | 0 个 |

**根因**：三层链路均有缺口——蓝图规范不定义 tab 面板内容、上游 skill 不要求生成状态、下游 skill 不检查状态覆盖。

---

## 设计决策

### 1. 呈现形式：单文件 CSS 切换

所有状态在同一 HTML 文件中，用纯 CSS 机制切换：

| 状态类型 | CSS 机制 | 理由 |
|----------|---------|------|
| Tab 面板 | `input[type="radio"]` + `:checked` 兄弟选择器 | 天然互斥、语义正确、无 JS |
| Modal / Drawer / Sheet | `input[type="checkbox"]` + `:checked` | 可独立开关、支持多个同时存在 |
| 状态变体（empty/loading/error） | `<details>` 元素 | 语义化、原生可展开、可访问性佳 |

共享 CSS 放在 `prototype-toggles.css`，所有页面复用。

### 2. State Coverage Index

每个原型 HTML 顶部注入机器可读注释块，列出本页面应有的所有 UI 状态：

- `[✓]` 已渲染，`[ ]` 未定义
- Tab 面板必须全部 `[✓]`
- Overlays 覆盖蓝图中有交互设计的
- State Variants：empty + loading + error 全量生成，无例外

用途：CREATE 阶段作为生成清单，审查阶段作为验收清单。

### 3. CREATE 阶段增强

扩展 Phase 0.5 流程：

```
读蓝图 → 解析所有 tab/overlay/state 定义
  → 生成默认态（主面板 + active tab）
  → 生成所有非 active tab 面板内容
  → 生成蓝图定义的 overlay（Modal/Drawer/Sheet）
  → 生成所有状态变体（empty + loading + error，全量）
  → 注入 State Coverage Index
  → 注入 CSS 切换系统
```

蓝图内容不足时的分级处理：

| 蓝图完整度 | 策略 |
|-----------|------|
| 有子模块清单 | 按清单生成 mock 数据面板 |
| 有标签名 + 页面上下文可推断 | 推理生成合理内容 |
| 仅有标签名 + 无法推断 | 生成骨架占位 + 标注 `[待 PM 定义]` |

所有推理生成的内容标注 `<!-- ⚠️ 内容基于上下文推理，未经 PM 确认 -->`。

### 4. 蓝图上游规范补全

业界三层分离模型：产品规格 → 交互设计 → 视觉原型。

当前 Ditto 的问题是第二层（交互设计）被压缩进第一层（产品规格）。

**蓝图格式升级**——每个页面增加三个结构化章节：

1. **Tab Content Section**：每个 tab 列出子模块 + 数据字段 + 交互说明
2. **Overlay Registry**：列出所有 Modal/Drawer/Sheet + 触发条件 + 内容
3. **Component × State Matrix**：把 `04_interaction_state_spec.md` 的通用状态映射到本页组件

```markdown
## Signals Inbox — 组件 × 状态矩阵

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Signal Table | 待复核列表 | skeleton 行 | "暂无待复核信号" + CTA | 重试按钮 | 黄色边框 | 行高亮 + 右面板联动 | 多选栏 + 批量操作 |
| Signal Detail | 隐藏 | — | — | — | — | 显示详情面板 | — |
| Order Sheet | — | — | — | — | — | 按钮可用 | "批量生成" |
```

### 5. 协作闭环

```
ditto-product-arch --create/--iterate
  → 产出完整蓝图（含 tab 内容 + overlay + 状态矩阵）
    → ditto-design-cycle --create
      → 产出全状态原型
        → 审查发现蓝图缺失
          → 反馈回 ditto-product-arch
```

---

## 改造清单

| # | 文件 | 改造内容 | 优先级 |
|---|------|---------|--------|
| 1 | `prototype/shared/prototype-toggles.css` | **新建**：共享 CSS 切换系统 | P0 |
| 2 | `.claude/commands/ditto-design-cycle.md` | Phase 0.5 全状态生成 + State Coverage Index + Phase 1/3 状态覆盖检查 | P0 |
| 3 | `.claude/design-review/templates.md` | Agent 输出增加「状态覆盖完整度」检查项 | P0 |
| 4 | `.claude/commands/ditto-product-arch.md` | 蓝图产出格式要求（Tab/Overlay/Matrix）+ `--audit` 增加状态覆盖维度 | P1 |
| 5 | `design/specs/02_core_page_blueprints.md` | 蓝图格式升级：17 个页面补充 tab 面板内容和状态矩阵 | P1 |
| 6 | `design/specs/04_interaction_state_spec.md` | 增加「页面状态映射示例」章节 | P2 |

## 不改什么

- 现有已 done 的 7 个原型不回溯改造（下次 --create-all 时自然覆盖）
- 六角色审查分工不变，只增加检查维度
- Model 路由策略不变
