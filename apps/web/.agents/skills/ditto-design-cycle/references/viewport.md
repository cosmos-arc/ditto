# 多视口检测

> **所有涉及 HTML 原型的 review 必须在目标视口下验证内容完整性。** 宿主可用的浏览器开发者工具 默认视口通常远大于设计目标，导致内容截断问题无法被发现。

---

## 标准视口矩阵

| 标识 | 分辨率 | 用途 | Chrome emulate 参数 |
|------|--------|------|-------------------|
| `VP-LARGE` | 1920x1080 | 大屏桌面（主要设计目标） | `1920x1080` |
| `VP-STANDARD` | **1536x1080** | **标准桌面（默认审查视口）** | `1536x1080` |
| `VP-COMPACT` | 1366x768 | 笔记本（最小桌面支持） | `1366x768` |

> **默认审查视口**: `VP-STANDARD` (1536x1080)。所有截图、评分、Token 审计均在此视口下进行。
> 宿主可用的浏览器开发者工具 的实际可用视口通常比 emulate 参数更大（如 1536x1080 emulation → 1707x1200 actual），这是因为 emulation 不改变浏览器窗口大小而是设置布局视口。**因此必须使用 `emulate` 工具设置视口，而非依赖默认窗口大小。**

---

## Phase 1: BASELINE（多视口基线）

```
Phase 1 BASELINE 多视口扩展：
  │
  ├─ Step 1: 设置默认审查视口 VP-STANDARD (1536x1080)
  │   → 宿主可用的浏览器工具: emulate(viewport="1536x1080")
  │   → navigate_page(reload, ignoreCache=true)
  │
  ├─ Step 2: 内容溢出检测（evaluate_script）
  │   → 检查 body.scrollHeight vs window.innerHeight
  │   → 检查 body overflow 属性
  │   → 如果 scrollHeight > innerHeight 且 overflow 为 hidden:
  │     → 记录为 UX P0: 内容截断
  │     → 计算截断像素数
  │
  ├─ Step 3: 关键元素可见性检测（evaluate_script）
  │   → 遍历页面关键容器（main-content, tab-band, footer 等）
  │   → 检查每个元素的 getBoundingClientRect().bottom <= window.innerHeight
  │   → 记录不可见元素列表
  │
  └─ Step 4: 最小视口抽检 VP-COMPACT (1366x768)
      → 宿主可用的浏览器工具: emulate(viewport="1366x768")
      → navigate_page(reload, ignoreCache=true)
      → 重复 Step 2-3
      → 记录截断情况
      → 恢复 VP-STANDARD
```

---

## Phase 7: FINAL（多视口验证）

```
Phase 7 FINAL 多视口扩展：
  │
  ├─ Step 1: VP-STANDARD (1536x1080) 完整性验证
  │   → 所有内容无截断
  │   → 滚动行为正常（如果需要滚动）
  │   → sticky 元素正常工作
  │
  ├─ Step 2: VP-COMPACT (1366x768) 完整性验证
  │   → 可滚动到底部
  │   → 底部内容完全可见
  │   → 布局无破坏
  │
  └─ Step 3: 输出视口验证报告
      → 嵌入审查报告「视口验证」章节
```

---

## 评估脚本（evaluate_script 模板）

```javascript
// 多视口内容完整性检测
() => {
  const body = document.body;
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  const bodyStyle = getComputedStyle(body);
  const scrollHeight = body.scrollHeight;

  // 查找所有可能被截断的关键容器
  const keyContainers = document.querySelectorAll(
    '.main-content, .tab-band, .tab-content, footer, ' +
    '[role="tabpanel"], .panel-body, .table-container'
  );

  const hiddenElements = [];
  keyContainers.forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.bottom > viewport.h) {
      hiddenElements.push({
        selector: el.className || el.tagName,
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        cutoff: Math.round(rect.bottom - viewport.h)
      });
    }
  });

  return {
    viewport,
    scrollHeight: Math.round(scrollHeight),
    overflow: bodyStyle.overflow,
    overflowY: bodyStyle.overflowY,
    canScroll: scrollHeight > viewport.h,
    hasHiddenContent: hiddenElements.length > 0,
    hiddenElements,
    cutoffPixels: hiddenElements.length > 0
      ? Math.max(...hiddenElements.map(e => e.cutoff))
      : 0
  };
}
```

---

## UX P0 规则

以下情况**自动标记为 UX P0**：

| 条件 | 严重性 | 说明 |
|------|--------|------|
| `body { overflow: hidden }` 且 `scrollHeight > viewport` | **P0** | 内容被截断，用户无法访问 |
| 关键交互元素（tab/content/footer）在 VP-STANDARD 下不可见 | **P0** | 核心内容丢失 |
| 关键元素在 VP-COMPACT 下不可见且无法滚动到底 | **P0** | 最小支持视口下功能不可用 |
| VP-COMPACT 下需滚动才能看到底部内容 | **P1** | 可接受但需确认滚动体验流畅 |

---

## Fixed/Sticky 元素遮挡检测

> **R9 教训**: scrollHeight ≤ viewport 通过了，但 fixed 定位的 status bar 遮挡了 23px 内容。
> viewport 验证必须包含 z-index 层叠遮挡检测。

### 检测脚本

```javascript
// Fixed/Sticky 元素遮挡检测
() => {
  const allEls = document.querySelectorAll('body *');
  const fixedEls = [];
  const stickyEls = [];

  allEls.forEach(el => {
    const pos = getComputedStyle(el).position;
    if (pos === 'fixed') fixedEls.push(el);
    if (pos === 'sticky') stickyEls.push(el);
  });

  const overlaps = [];
  fixedEls.forEach(fixEl => {
    const fr = fixEl.getBoundingClientRect();
    allEls.forEach(el => {
      if (el === fixEl || fixedEls.includes(el) || stickyEls.includes(el)) return;
      // 跳过 fixed 元素的子元素
      if (fixEl.contains(el)) return;
      const er = el.getBoundingClientRect();
      // 矩形重叠检测
      if (er.right > fr.left && er.left < fr.right &&
          er.bottom > fr.top && er.top < fr.bottom) {
        const overlapH = Math.min(er.bottom, fr.bottom) - Math.max(er.top, fr.top);
        const overlapW = Math.min(er.right, fr.right) - Math.max(er.left, fr.left);
        if (overlapH > 5 && overlapW > 5) {
          overlaps.push({
            fixed: (fixEl.className || fixEl.tagName).toString().substring(0, 40),
            overlapped: (el.className || el.tagName).toString().substring(0, 40),
            overlapH: Math.round(overlapH) + 'px',
            overlapW: Math.round(overlapW) + 'px',
            severity: overlapH >= 20 ? 'P0' : 'P1'
          });
        }
      }
    });
  });

  // 检查 fixed 元素是否有 padding 补偿
  const bodyStyle = getComputedStyle(document.body);
  const bodyPadBottom = parseInt(bodyStyle.paddingBottom) || 0;
  const bodyPadTop = parseInt(bodyStyle.paddingTop) || 0;
  const maxFixedBottom = fixedEls.reduce((max, el) => {
    const h = parseFloat(getComputedStyle(el).height);
    return el.getBoundingClientRect().top > window.innerHeight / 2 ? Math.max(max, h) : max;
  }, 0);

  return {
    fixedCount: fixedEls.length,
    stickyCount: stickyEls.length,
    overlaps,
    bodyPaddingBottom: bodyPadBottom,
    bodyPaddingTop: bodyPadTop,
    maxFixedElementHeight: Math.round(maxFixedBottom),
    paddingCompensates: bodyPadBottom >= Math.round(maxFixedBottom)
  };
}
```

### 遮挡 P0 规则

| 条件 | 严重性 | 说明 |
|------|--------|------|
| Fixed 元素遮挡内容 ≥ 20px | **P0** | 关键内容不可见 |
| Fixed 元素遮挡内容 5-20px | **P1** | 部分内容被遮挡 |
| Fixed 元素无 padding 补偿 | **P1** | 潜在遮挡风险 |
| Sticky 元素堆叠高度异常 | **P1** | header + context-bar 累积高度超出预期 |

---

## 报告输出格式

在审查报告中增加「视口验证」章节：

```markdown
## 视口验证

| 视口 | 分辨率 | 内容完整 | 截断(px) | 可滚动 | sticky 正常 | 状态 |
|------|--------|---------|---------|--------|------------|------|
| VP-STANDARD | 1536x1080 | ✓ | 0 | N/A | ✓ | 通过 |
| VP-COMPACT | 1366x768 | ✓ (滚动后) | 130 | ✓ | ✓ | 通过 |

**body overflow**: hidden → auto（页面级覆写）
**截断修复**: `body { overflow-y: auto; }` 已添加
```
