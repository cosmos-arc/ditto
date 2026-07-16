---
paths:
  - "docs/designs/specs/prototypes/**/*.html"
  - "src/**/*.{tsx,jsx}"
---

# 零 Inline Style 规则

> **铁律**：所有 HTML/JSX 文件中禁止使用 `style="..."` 属性。零容忍，无例外。

## 原因

1. **设计一致性**：inline style 绕过 Design Token 体系，导致视觉漂移
2. **可维护性**：散落在 HTML 中的样式无法集中审查和修改
3. **Prototype ↔ React 对齐**：inline style 不会被 L1 Token 检测捕获

## 唯一正确做法

### Prototype (HTML)

```html
<!-- ❌ 禁止 -->
<div style="color: var(--text-tertiary); width: 78%;">...</div>

<!-- ✅ 正确 -->
<div class="color-tertiary flow-w-78">...</div>
```

- 使用 `layout-base.css` 中的共享工具类（`.color-*`, `.flex-*`, `.flow-w-*`, `.sk-h-*` 等）
- 页面特有的样式在页面 `<style>` 块中定义类，然后引用
- `display:none` 用 `aria-hidden="true"` + CSS `[aria-hidden="true"] { display: none; }` 或 `.hidden`
- 百分比宽度用 `.flow-w-N` / `.w-N` 工具类
- SVG noise filter 用 `.noise-svg-source`

### React (TSX)

```tsx
// ❌ 禁止
<div style={{ width: '78%' }}>...</div>

// ✅ 正确
<div className="w-[78%]">...</div>
```

- 使用 Tailwind CSS utility classes
- 需要精确像素值时用 `w-[Npx]` / `h-[Npx]` 语法
- 动态值通过 CSS 变量 + Tailwind arbitrary value 实现

## 常见 inline style → class 替换映射

| Inline Style | 替换为 |
|---|---|
| `style="color: var(--text-tertiary);"` | `.color-tertiary` |
| `style="color: var(--text-primary);"` | `.color-primary` |
| `style="color: var(--market-up-fg);"` | `.color-market-up` |
| `style="flex: 1;"` | `.flex-1` |
| `style="flex-shrink: 0;"` | `.flex-shrink-0` |
| `style="width:100%;"` | `.w-full` |
| `style="display:none;"` | `.hidden` 或 `aria-hidden="true"` |
| `style="position:absolute;width:0;height:0"` | `.noise-svg-source` |
| `style="width:78%"` (flow bar) | `.flow-w-78` |
| `style="height:3px"` (skeleton) | `.sk-h-3` |

## 审查门禁

每次 review 或修改 prototype 后，运行：

```bash
# 验证零 inline style
grep -rn 'style="' docs/designs/specs/prototypes/page-*.html | grep -v '^\s*//' | grep -v '/\*' | grep -v 'replaces style='
# 期望输出：空（0 行）
```

如有任何命中，必须修复后才能标记 review 通过。
