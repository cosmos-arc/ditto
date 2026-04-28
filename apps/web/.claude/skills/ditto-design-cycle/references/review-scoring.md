# 审查评分标准

> **核心原则**: 审查标准必须与产品功能定位、模块角色、用户场景匹配。
> 不是用通用 UI 准则打分，而是用「这个产品应该长什么样」的标准评估。
>
> **产品规格详见**: [docs/designs/specs/00_ditto_product_criteria.md](../../../docs/designs/specs/00_ditto_product_criteria.md)
> 本文档仅包含审查评分相关的量化指标和检查清单。

---

## PRE-SCORE GATES（评分前置门禁）

> **宏观布局正确是评分的前提。以下门禁全部通过后才能进行五维度评分。任何一项不通过 = 布局错误，不计分。**
>
> **可执行门禁**：
>
> ```bash
> bun run prototype:gates -- --prototype docs/designs/specs/prototypes/<page>.html
> ```
>
> 该命令必须在评分前运行；exit code 非 0 表示存在阻断问题，不能继续评分。

### Gate 0: 原型工具 UI 隔离（P0）

| 检查项 | 验证方法 | 通过标准 |
|--------|---------|---------|
| `.proto-nav` 不可见或不在 default-view 中 | Playwright `getBoundingClientRect().height === 0` 或在 `#states-gallery`/`#overlays-gallery` 内 | 不可见 |
| `.style-label` 不可见 | 同上 | 不可见 |
| `.skip-link` 不可见 | 同上（仅 `:focus` 时可见是允许的） | 默认不可见 |

### Gate 1: CSS 资源完整加载（P0）

| 检查项 | 验证方法 | 通过标准 |
|--------|---------|---------|
| Token CSS 已加载 | `document.querySelectorAll('link')[].sheet.cssRules.length > 0` | 所有 token 文件 rules > 0 |
| 无 404 错误 | Console 无 `Failed to load resource` | 0 个 404 |
| CSS 变量可用 | `getComputedStyle(document.documentElement).getPropertyValue('--font-size-12')` 非空 | 关键 token 有值 |

### Gate 2: Shell 网格结构正确（P0）

| 检查项 | 验证方法 | 通过标准 |
|--------|---------|---------|
| Shell 为 grid 布局 | `getComputedStyle(.shell-*).display === 'grid'` | grid |
| Grid 列数正确 | `gridTemplateColumns.split(' ').length >= 2` | ≥ 2 列 |
| 各区域可见 | rail / header / main / sidebar 的 `getBoundingClientRect().height > 0` | 全部可见 |

### Gate 3: 浏览器视觉验证（P0）

> **必须执行 `browser_take_screenshot` 并人工/AI 视觉检查。** 纯 `getComputedStyle()` 验证不能替代视觉检查。

| 检查项 | 方法 |
|--------|------|
| 页面整体布局是否符合预期 | 截图 + AI vision 分析 |
| 无元素错位/重叠/溢出 | 截图检查 |
| 原型工具 UI 未污染产品视图 | 截图中无 proto-nav/style-label |

### Gate 4: 交互功能完整性（P0）

> **所有可交互元素必须真实可用，不能只是视觉存在。** 仅靠 DOM 结构和 CSS 规则推断交互功能是不够的——必须在浏览器中实际触发并验证状态变化。

#### 验证范围

```
交互元素清单（Playwright 程序化验证）：
├─ 1. Tab 切换：每个 tab-group 的所有 tab label 必须可点击，点击后对应面板可见
├─ 2. Overlay 开闭：每个 overlay 的触发器和关闭机制必须工作
├─ 3. Toggle 开关：radio/checkbox 驱动的视图切换（如 Treemap↔Heatmap）必须实际生效
├─ 4. Hover 反馈：可交互元素（treemap cell、queue item 等）必须有 hover 视觉响应
└─ 5. 状态视图切换：三区 radio（default/states/overlays）必须正确切换可见性
```

#### 验证方法

> 以下验证通过 Playwright `page.evaluate()` 程序化执行，不需要截图或 vision 模型。

```javascript
// 通用模式：验证 CSS :has() 驱动的状态切换
async function verifyToggle(page, radioId, expectedVisibleSelector, expectedHiddenSelector) {
  // 初始状态检查
  const beforeVisible = await page.$eval(expectedVisibleSelector, el =>
    getComputedStyle(el).display !== 'none');
  if (!beforeVisible) return { pass: false, reason: `${expectedVisibleSelector} not visible initially` };

  // 切换状态
  await page.evaluate(id => {
    document.getElementById(id).checked = true;
    // 触发 change 事件确保 :has() 重算
    document.getElementById(id).dispatchEvent(new Event('change', { bubbles: true }));
  }, radioId);

  // 验证切换结果
  const afterVisible = await page.$eval(expectedVisibleSelector, el =>
    getComputedStyle(el).display !== 'none');
  const afterHidden = await page.$eval(expectedHiddenSelector, el =>
    getComputedStyle(el).display === 'none');

  return { pass: afterVisible && afterHidden };
}
```

#### 量化检查项

| 检查项 | 验证方法 | 通过标准 |
|--------|---------|---------|
| Tab 面板切换 | 逐一点击 tab label，检查对应面板 `display !== 'none'` | 每个 tab 点击后面板切换正确 |
| Overlay 打开 | 触发 overlay 打开操作（radio checked / click handler），检查 overlay `display !== 'none'` | overlay 可见 |
| Overlay 关闭 | 触发关闭操作（关闭按钮 / ESC / radio unchecked），检查 overlay `display === 'none'` | overlay 不可见 |
| Toggle 视图切换 | 设置 radio checked，检查目标视图 `display !== 'none'` 且旧视图 `display === 'none'` | 视图正确切换 |
| 三区 radio 切换 | 切换 default/states/overlays radio，检查对应 zone 可见 | zone 正确切换 |
| Hover 视觉反馈 | `page.hover(el)` 后检查 `getComputedStyle()` 是否有变化（opacity/border/shadow 等） | 至少 1 个 computed style 值变化 |
| 交互元素可达性 | `querySelectorAll('button, [role="button"], label[for], [tabindex]')` | 所有元素 `pointer-events !== 'none'`（非禁用态） |

#### 实施要求

1. **Phase 1 自动发现**：在基线采集中自动扫描所有交互元素（radio group、tab label、overlay trigger），生成「交互元素清单」
2. **Phase 8 Gate 4 验证**：在评分前对清单中的每个元素执行上述验证
3. **验证脚本化**：鼓励将验证逻辑封装为可复用脚本，避免人工遗漏
4. **部分失败降级**：若 ≥ 50% 交互元素通过 → 降分处理（扣除 1-2 分）；< 50% → STOP 修复

#### 失败处理

- Gate 0 不通过：**STOP**，修复原型工具 UI 隔离后再评分
- Gate 1 不通过：**STOP**，修复 CSS 加载问题（通常是 HTTP 服务器目录错误）
- Gate 2 不通过：**STOP**，修复 shell 布局后再评分
- Gate 3 不通过：**降分处理**，根据视觉问题严重程度扣除 1-3 分
- Gate 4 不通过（< 50%）：**STOP**，修复交互功能后再评分
- Gate 4 不通过（≥ 50%）：**降分处理**，扣除 1-2 分

---

## Fixed/Sticky 元素遮挡检测

> viewport 验证不能只看 scrollHeight，必须检测 z-index 层叠遮挡。

### 检测规则

```
遮挡检测（viewport 验证必须包含）：
├─ 1. 列出所有 position:fixed 和 position:sticky 元素
├─ 2. 对每个 fixed/sticky 元素，检测其矩形是否与任何非 fixed/sticky 元素重叠
├─ 3. 重叠 > 5px → 标记为 P1（内容被遮挡）
├─ 4. 重叠 > 20px → 标记为 P0（关键内容不可见）
└─ 5. fixed 元素必须检查 body 是否有对应的 padding/margin 补偿
```

### 常见陷阱

| 陷阱 | 表现 | 修复 |
|------|------|------|
| Fixed footer 无补偿 | 底部内容被 footer 遮挡 | `body { padding-bottom: {footer-height} }` |
| Fixed header 无补偿 | 顶部锚点跳转后内容被遮挡 | `scroll-margin-top: {header-height}` |
| 多个 sticky 元素堆叠 | header + context-bar 的 sticky 区域叠加 | 确保 sticky top 值累加正确 |
| 原型标注遮挡 | style-label 遮挡产品 UI | `pointer-events: none` + z-index 管理 |

---

## 信息密度指标

> 金融终端的信息密度不是"越多越好"，而是"有效信息密度"。
> 指标基于 [00_ditto_product_criteria.md](../../../docs/designs/specs/00_ditto_product_criteria.md) 中的密度准则。

### 量化指标

| 指标 | 计算方法 | 目标值 |
|------|---------|--------|
| 文字密度 | 总文字字符数 / 内容区面积(Kpx) | **≥ 12 chars/Kpx** |
| 数据点密度 | 数值型数据点数量 / 主内容区面积(Kpx) | **≥ 3 data-points/Kpx** |
| 可扫视性 | 用户扫视一次（2-3秒）能获取多少独立信息块 | **≥ 8 信息块** |
| 空间利用率 | 非留白区域面积 / 总内容区面积 | **≥ 70%** |

### 注意

- 这些指标与 AD 的「留白 ≥35%」存在张力。在金融终端页面中，**信息效率指标优先于留白指标**。
- AD 阈值中的「留白 ≥35%」仅适用于 L3 装饰区，不适用于 L1/L2 数据区。

---

## 评分维度

### 原有 4 维度（美学）

| 维度 | 权重 | 说明 |
|------|------|------|
| 克制度 | 20% | 字号/装饰/色彩的种类数和克制程度 |
| 一致性 | 20% | Token/字体/间距/阴影的系统一致性 |
| 高级感 | 20% | 材质感/动效/数据可视化的 sophistication |
| 品牌方向 | 20% | Bloomberg/quant desk DNA 的体现程度 |

### 第 5 维度（功能）

| 维度 | 权重 | 说明 |
|------|------|------|
| **信息效率** | **20%** | 信息密度、可扫视性、交互可达性、模块角色适配性 |

### 第 6 维度（DESIGN.md 一致性）

| 维度 | 权重 | 说明 |
|------|------|------|
| **DESIGN.md 一致性** | **附加分** | 原型的组件 token 使用是否与 DESIGN.md Components 章节一致 |

**评分细则**：

| 检查项 | 量化方法 | 满分条件 |
|--------|---------|---------|
| Components token 映射 | 原型组件使用的 token 是否存在于 DESIGN.md Components 章节 | 全部匹配 |
| Typography 角色对应 | 字号/字重使用是否符合 DESIGN.md Typography 4 角色系统 | 0 违规 |
| Domain 签名色规范 | 域签名色使用是否符合 DESIGN.md Domain Identity 规则 | 0 跨域混用 |
| Do's and Don'ts 合规 | 是否违反 DESIGN.md Do's and Don'ts 章节的任何禁止项 | 0 违规 |

**计算方式**：本维度作为附加分，不影响 5 维度基础评分。违规时在审查报告中标注 `[DESIGN.md drift]` 并列出具体偏差。

### 综合气质评分卡

```
气质评分卡：
├─ 克制度:    ████████░░ 8.2/10
├─ 一致性:    ███████░░░ 7.5/10
├─ 高级感:    ████████░░ 8.0/10
├─ 品牌方向:  ████████░░ 8.3/10
├─ 信息效率:  ████████░░ 7.8/10
└─ 综合气质:  ████████░░ 8.0/10
```

### 信息效率评分细则

| 检查项 | 量化方法 | 满分条件 |
|--------|---------|---------|
| 信息密度 | chars/Kpx ≥ 12 | +2.0 |
| 交互元素适配 | 所有交互元素字号 ≥ 12px，高度 ≥ 24px | +2.0 |
| 模块分层密度 | L1 高密度 / L2 中密度 / L3 克制 | +2.0 |
| 间距梯度 | 模块间间距按层级递减，无固定大间距 | +2.0 |
| Token 消费率 | 页面 var() 使用率 ≥ 80%, hardcoded = 0 | +2.0 |

---

## 量化平台专用准则

> 以下准则针对 Ditto 作为金融终端工具的特殊定位，补充通用 UI 审查未覆盖的维度。

### 数据新鲜度视觉反馈

| 检查项 | 量化方法 | 阈值 | 优先级 |
|--------|---------|------|--------|
| 数据老化标识 | 实时数据元素是否随时间衰减（opacity/fade） | 使用 `--data-freshness-*` token | P1 |
| 连接状态反馈 | 数据源状态（live/updating/stale/disconnected）是否可见 | 状态指示器可见 | P1 |
| 延迟标识 | 数据延迟超过阈值时是否有视觉标识 | 延迟 ≥ 5s 时出现标识 | P2 |

### 色觉无障碍（Color Accessibility）

| 检查项 | 量化方法 | 阈值 | 优先级 |
|--------|---------|------|--------|
| 涨跌色非纯色觉依赖 | 涨跌信息是否同时使用颜色 + 形状/位置/图标 | 涨跌必须配合 ▲/▼ 或上下位置 | P0 |
| 资产类别色彩辨识 | 7 种资产类别色在色盲模拟下的区分度 | Paul Tol bright scheme 已验证 | P1 |
| 热力图灰度可读性 | 热力图在灰度模式下是否保持方向性 | 亮度单调递增/递减 | P2 |

### Token 消费率

| 检查项 | 量化方法 | 阈值 | 优先级 |
|--------|---------|------|--------|
| 页面 Token 使用率 | 使用 var(--*) 的声明 / 总声明数 | ≥ 80% | P1 |
| Hardcoded oklch 审计 | 直接使用 oklch() 的声明数 | 主页面 = 0 | P1 |
| Inline style 审计 | style="..." 属性数 | 主页面 ≤ 5 | P2 |

### 密度可切换性

| 检查项 | 量化方法 | 阈值 | 优先级 |
|--------|---------|------|--------|
| 密度属性声明 | 页面是否声明 data-density 属性 | 必须有 | P1 |
| 密度切换响应 | 切换 data-density 时布局是否正确响应 | 行高/间距/字号变化 | P1 |
| 3 档可用性 | dense/compact/comfortable 三档均无布局破坏 | 各档内容完整 | P2 |

---

## Data Viz Specialist 审查维度

> Data Viz Specialist 是七角色并行审查的独立角色（sonnet），不是 Art Director 的子集。
> 量化产品的数据可视化审查不应被兼顾，这是独立的专业维度。

### 审查清单

| 检查项 | 量化方法 | 阈值 | 优先级 |
|--------|---------|------|--------|
| 数据新鲜度反馈 | 实时数据是否有老化/衰减的视觉表达 | 使用 `--data-freshness-*` token | P1 |
| 图表 Token 使用 | sparkline/图表是否使用 `--chart-*` / `--sparkline-*` token | — | P1 |
| 色觉无障碍 | 涨跌信息是否不仅依赖颜色（是否配合 ▲/▼ 符号） | 涨跌必须配合形状辅助 | **P0** |
| 热力图/矩阵规范 | 条件格式是否使用 `--heatmap-*` scale | — | P1 |
| 资产类别色彩 | 跨市场组件是否使用 `--asset-*` 色彩体系 | — | P1 |
| 数据状态标识 | 连接/同步/断连状态是否通过 `--data-state-*` 表达 | 状态指示器可见 | P1 |
| Token 消费率 | 数据组件中 hardcoded 值是否收敛到 token | var() ≥ 80% | P1 |

### 三区审查指引

- **主要评估**: default-view 中数据组件的可视化质量
- **辅助评估**: states-gallery 中数据组件的三态表现（loading skeleton / empty 提示 / error 恢复）

### 使用工具

- Chrome DevTools MCP: 色盲模拟、对比度检测
- impeccable skills: `audit`

---

## 各角色审查清单补充

> 以下检查项是对 roles.md 中各角色基础清单的补充。
> 基础清单详见 [roles.md](roles.md)，本节仅列出审查迭代中发现的盲区。

### UX Reviewer 补充检查

| 检查项 | 说明 | 优先级 |
|--------|------|--------|
| 交互元素最小尺寸 | tab/button/link 高度 ≥ 24px | P0 |
| Fixed 元素遮挡 | 所有 fixed/sticky 元素无内容遮挡 | P0 |
| 10px 使用审计 | 10px 仅用于纯辅助信息，不用于交互/导航元素 | P1 |
| 小字号对比度 | 所有 ≤10px 元素 L ≥ 0.60 | P1 |

### Art Director 补充检查

| 检查项 | 说明 | 优先级 |
|--------|------|--------|
| 模块密度分层 | L1/L2/L3 各自符合密度准则（详见产品规格） | P1 |
| 间距梯度 | 模块间间距按信息层级递减（详见产品规格） | P1 |
| 信息效率评分 | 第 5 维度的量化评估 | P1 |

### Product Manager 补充检查

| 检查项 | 说明 | 优先级 |
|--------|------|--------|
| 业务规则正确性 | 涨跌色、排序逻辑、筛选条件等业务规则是否正确 | P0 |
| 空间利用率 | 内容区 ≥ 70% 被有效利用 | P1 |
| 数据可达性 | 核心数据不需要滚动即可见 | P1 |

### IA Specialist 补充检查

| 检查项 | 说明 | 优先级 |
|--------|------|--------|
| 内容分组逻辑 | 模块分组是否反映用户心智模型 | P1 |
| 导航可达性 | 从任何页面 ≤ 3 步到达目标信息 | P1 |
| 首屏信息优先级 | above fold 放置最重要信息 | P1 |
| Happy path 完整性 | 核心任务路径无断裂 | P0 |
| 死端检测 | 无出口的页面/状态 | P0 |
| 标签语义一致性 | 相同概念使用相同标签（跨页面） | P1 |

---

## 准则的持续优化

> 这些准则不是一成不变的。每次 review 后都应该回顾：
> - 哪些准则帮助发现了真实问题？（保留）
> - 哪些准则产生了误报？（调整阈值或删除）
> - 有哪些新问题没有对应的准则？（新增）
> - 产品定位是否有变化？（更新模块分层，同步到产品规格）

**优化原则**: 准则的修改基于实际审查经验，不是为了"更容易通过"而妥协。
