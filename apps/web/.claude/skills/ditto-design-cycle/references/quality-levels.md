# 质量等级

> 不同质量等级对应不同的 impeccable skills 组合。默认等级：`polished`。

---

## 等级定义

| 等级 | 标准 | 对应 impeccable skills |
|------|------|----------------------|
| **functional** | 正确渲染、可交互、无明显 bug、基本可访问 | — |
| **good** | Token 一致、响应式、布局合理、文案准确 | `normalize`, `arrange`, `clarify` |
| **polished** | 视觉层次清晰、节奏感、微交互、令人舒适 | + `colorize`, `typeset`, `animate` |
| **best** | 高级感、令人印象深刻、记忆点、业界领先 | + `bolder`, `delight`, `overdrive` |

---

## Phase 7 POLISH 中的应用

### Step 7.2: 按等级应用 impeccable skills

```bash
# good
impeccable:normalize → impeccable:arrange → impeccable:clarify

# polished（默认）
impeccable:normalize → impeccable:arrange → impeccable:clarify →
impeccable:colorize → impeccable:typeset → impeccable:animate

# best
impeccable:normalize → impeccable:arrange → impeccable:clarify →
impeccable:colorize → impeccable:typeset → impeccable:animate →
impeccable:bolder → impeccable:delight → impeccable:overdrive
```

### Step 7.3: Art Director 复审

- 可降级过度的 bolder/delight/overdrive 效果
- 可移除违反克制度的装饰元素
- 使用 impeccable: quieter 处理过度装饰

---

## Edition Review 质量门槛（2026-04-29）

从 `polished` 升级到 `best` 时，不再只看高级感和记忆点，还必须满足专家效率门槛：

| 等级 | 额外要求 |
|------|----------|
| **polished** | 关键页面通过 prototype gates；light / density 可切换；状态、overlay 和交互可用。 |
| **best** | 7 类 Shell 代表页有 dark / light + compact / comfortable 截图矩阵；专家入口页有 `data-primary-answer`；关键数据图有非颜色编码；高风险动作有确认链路；Bottom Tray 不遮挡主流程。 |

`best` 不是“更炫”，而是更可靠、更可扫视、更像专家每天愿意使用的工作台。
