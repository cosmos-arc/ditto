# Phase 12: IMPLEMENT — TDD 实现

> 严格 RED → GREEN → REFACTOR，可按组件并行拆分。

**输入**：Phase 11 架构文档 + Phase 10 度量数据 + contract JSON states 列表

---

## 执行策略

### 1. 组件粒度拆分

- 根据架构文档的组件树，将独立组件拆分为并行子任务
- 只有互不写同一文件、接口已经冻结的独立组件才适合使用宿主原生并行能力
- 共享组件（如 Layout、shell）由单个 agent 负责，不并行

### 2. TDD 循环（每个组件）

```
RED       → 写失败测试（渲染结构 + slots + 关键 props）
GREEN     → 最少代码让测试通过
CHECK     → 度量对齐（对比 Phase 10 数据，偏差 < 3%）
SIMPLIFY  → 删除重复、降低分支复杂度并收紧接口
REFACTOR  → 消除重复，提取复用
```

### 3. 布局实现铁律

- 每个 `[data-slot]` 区域的尺寸必须与 Phase 10 度量一致
- grid-template / flex 分配值从度量数据精确复制
- 禁止猜测：无法从度量推导的值 → 回退 Phase 11 询问
- content-driven 区域不设高度约束

### 4. 状态覆盖实现

按 contract JSON 的 `states.universal` + `states.pageSpecific` 逐个实现：

| 状态 | 实现 |
|------|------|
| `loading` | skeleton / spinner |
| `empty` | 空状态 UI |
| `error` | 错误边界 + fallback |
| `stale` | 数据过期指示 |
| domain-specific | 来自 `states.pageSpecific` |

- 实现 contract 中定义的 `interactions[]`（如 sidebar-toggle 交互）
- 每个状态至少一个测试用例

### 5. Slot 一致性验证

- 每个组件渲染的 `data-slot` 属性必须与 contract 的 `slots[]`（required=true）完全匹配
- 同时验证 `subSlots[].reactSelector` 在 React 中存在对应组件
- 多余或缺失的 slot 视为 P0 阻断项

---

## 并行规则

- 独立组件（无共享状态的 leaf 组件）→ 并行
- 共享 Layout / 父组件 → 串行优先
- 依赖组件（需要另一个组件的 props 类型）→ 按拓扑排序

---

## Phase 12.5: Layout Smoke Test

> Phase 12 所有组件的 TDD 循环完成后自动触发。30 秒快速验证，捕获结构性布局错误。

### 执行步骤

```
1. 启动 React dev server（如果未运行）

2. Playwright 启动 + 加载 React 页面
   chromium.launch({ channel: 'chromium' })

3. 提取关键区域 bounding rect
   selector 来源：contract shell slots（required=true）
   每个 shell slot：x, y, width, height

4. 与 Phase 10 度量数据对比
   通过标准：宽度偏差 < 5%，高度偏差 < 8%

5. 结果
   ├─ 全部通过 → 输出摘要，继续 Phase 13
   └─ 存在失败 → 输出偏差报告 + 定向修复
        ├─ 偏差 < 15% → 内联修复（调整 CSS）
        ├─ 偏差 15-30% → 回退对应组件的 TDD 循环
        └─ 偏差 > 30% → 回退 Phase 11 重新评估
```

### 与 Phase 14 的区别

| 维度 | Phase 12.5 Smoke | Phase 14 Verify |
|------|:---:|:---:|
| 检查范围 | shell slots only | shell slots + content subSlots |
| L1 Token | ❌ | ✅ |
| L2 Layout | 粗粒度（shell only） | 细粒度（全部 selector） |
| L3 Pixel | ❌ | ✅ |
| 阈值 | 宽松（5%/8%） | 严格（3%/5%） |
| 耗时 | ~30s | ~3min |
| 失败处理 | 定向修复 | Gap 分析 + 回退路由 |
