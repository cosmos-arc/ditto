# 视觉还原验证规范

> **铁律**：Token 正确 ≠ 视觉正确。布局比例错误比 token 错误更严重，因为后者可被测试捕获，前者不能。

---

## 核心原则

### 1. 三层验证模型

| 层级 | 验证内容 | 工具 | 通过标准 |
|------|---------|------|---------|
| **L1 Token** | token 引用合规 | 合规测试（grep） | 0 违规 |
| **L2 布局** | 元素尺寸与 prototype 一致 | evaluate_script 提取 bounding rect | 偏差 < 20% |
| **L3 像素** | 整体视觉对齐 | UI diff 截图对比 | 匹配度 > 90% |

**必须三层全部通过才能声称"原型对齐"。**

### 2. 禁止的验证方式

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| AI vision 泛化描述对比（"都是深色仪表盘"） | 逐元素 bounding rect 数值对比 |
| 只看 token 是否正确就声称视觉一致 | 同时验证布局比例 |
| "bun run check 通过" = 原型对齐 | 工程通过 ≠ 视觉对齐 |
| 截图 "看起来差不多" | UI diff 工具做像素级差异检测 |
| 只对比颜色值（oklch 一致） | 同时对比尺寸、位置、间距 |

---

## 强制流程

### 实现前：度量 Prototype

**在写任何 React 代码之前，必须先从 prototype HTML 提取布局度量。**

```bash
# 1. 用 HTTP 服务器启动 prototype HTML
cd docs/designs/specs/prototypes && python3 -m http.server 8888

# 2. 用 evaluate_script 提取关键区域度量
```

**必须提取的度量数据**：

```javascript
// 在 prototype 页面执行
() => {
  const items = [];
  document.querySelectorAll('.panel, .decision-banner, .panel-grow, .context-rail, .shell-main, .main-primary, .secondary-grid').forEach(el => {
    const rect = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    items.push({
      cls: el.className.substring(0, 60),
      x: Math.round(rect.x), y: Math.round(rect.y),
      w: Math.round(rect.width), h: Math.round(rect.height),
      display: cs.display,
      gridCols: cs.gridTemplateColumns?.substring(0, 80),
      gridRows: cs.gridTemplateRows?.substring(0, 80),
      flex: cs.flex,
      padding: cs.padding,
      gap: cs.gap,
    });
  });
  return items;
}
```

**必须记录到页面合同的度量字段**：

```
每个 section 必须记录：
- 实际像素高度（h）
- 布局策略（content-driven / flex-N / fixed-Npx / percentage）
- grid-template 值
- padding / gap 值
```

### 实现中：禁止无依据的百分比

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| `max-h-[66%]` 无 prototype 依据 | 从 prototype 提取实际像素高度，反推策略 |
| `h-[50%]` 猜测比例 | prototype 用 content-driven → React 也用 content-driven |
| `flex-[2_1_0]` 随意分配 | 从 prototype 的 grid-template 值精确复制 |

**判断规则**：

1. 如果 prototype 用 `1fr` → React 用 `flex-1`
2. 如果 prototype 用固定 `px` → React 用对应 token 或固定值
3. 如果 prototype 用 `auto`（内容驱动）→ React 不设高度约束
4. **如果 prototype 没有百分比布局 → React 也不要用百分比**

### 实现后：三层验证

#### L1：Token 验证（自动）

```bash
bun run test --run src/features/shell/design-system-compliance.test.ts
```

#### L2：布局验证（手动但强制）

**在 prototype 和 React 页面分别执行 evaluate_script，对比 bounding rect：**

```javascript
// 在两个页面分别执行，然后 diff 结果
() => {
  const results = {};
  // 提取每个命名区域的尺寸
  document.querySelectorAll('[data-slot], [class*="panel"], [class*="banner"], [class*="section"]').forEach(el => {
    const rect = el.getBoundingClientRect();
    results[el.dataset.slot || el.className.split(' ')[0]] = {
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    };
  });
  return results;
}
```

**通过标准**：每个对应区域的宽度偏差 < 3%，高度偏差 < 3%。

#### L3：像素验证（UI Diff）

使用 `ui_diff_check` 工具做像素级对比，要求匹配度 > 95%。

---

## 常见陷阱

### 陷阱 1："组件存在就够了"

组件存在 ≠ 布局正确。一个 `PriorityQueueSection` 渲染了 5 个 queue item，但如果容器给了 367px 而非 prototype 的 120px，信息密度就完全错了。

**检查方式**：对比每个 section 的实际渲染高度。

### 陷阱 2："grid-template 值一样就够了"

`grid-cols-[5fr_4fr_3fr]` 正确，但如果外层容器的高度分配错了（如 `max-h-[66%]`），内部 grid 再正确也没用。

**检查方式**：从最外层容器开始，逐层验证尺寸。

### 陷阱 3："颜色对了就对了"

所有 oklch 值完全一致，但 banner 高 180px vs prototype 149px，queue 高 367px vs prototype 120px——颜色正确但布局完全错位。

**检查方式**：先验证布局尺寸，再验证颜色。

---

## Checklist（实现每个 prototype-backed 页面前必过）

- [ ] 从 prototype HTML 提取了完整布局度量（grid-template, section 高度, flex 分配）
- [ ] 度量数据记录在页面合同或设计文档中
- [ ] React 实现的每个 section 布局策略（content-driven / flex / fixed）与 prototype 一致
- [ ] 没有使用无 prototype 依据的百分比高度/宽度
- [ ] L1 token 验证通过
- [ ] L2 布局验证通过（偏差 < 3%）
- [ ] L3 像素验证通过（匹配度 > 95%）
