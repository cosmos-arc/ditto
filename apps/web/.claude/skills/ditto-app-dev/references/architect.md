# Phase 11: ARCHITECT — 组件架构设计 [opus]

> 将度量数据转化为组件实现方案。这是最关键的决策环节。

**输入**：contract JSON（slots/subSlots/states/metrics.baseline/interactions/thresholds）+ 现有组件库

**执行步骤**：

1. **分析原型结构**
   - 将 prototype 的 DOM 结构映射到 React 组件树
   - 每个 prototype section → 一个 React 组件/子组件
   - 使用 contract 的 `subSlots[]` 识别页面级内容区块（如 main 下的 decision-banner、priority-queue）
   - 标记哪些 section 共享状态（如 Tab 切换、联动筛选）

2. **设计组件树**
   ```
   输出格式（示例 — analytical layout）：
   <AnalyticalLayout>
     <Strip />           ← 映射 [data-slot='strip']
     <Banner />          ← 映射 [data-slot='banner']
     <Main>
       <SectionA />      ← 映射 prototype .panel-xxx
       <SectionB />
       <SectionC />
     </Main>
     <Analysis />        ← 映射 [data-slot='analysis']
   </AnalyticalLayout>
   ```

3. **shadcn 组件映射**
   - 扫描组件需求 → 匹配 shadcn/ui 组件清单
   - 标记需要自定义的组件（prototype 中无直接对应）
   - 标记需要扩展的组件（在 shadcn 基础上添加功能）

4. **状态管理策略**
   - 服务端状态 → TanStack Query
   - 客户端 UI 状态 → 组件内 useState / Zustand（仅跨组件共享时）
   - 列出每个组件的输入 props 和状态

5. **复用策略**
   - Grep 现有 features/ 目录，识别可复用的组件/hooks
   - 标记需要新建 vs 复用 vs 扩展

6. **输出架构文档**
   - 组件树、状态管理方案、shadcn 映射、复用清单
   - 交给 Phase 12 的 TDD Developer 作为实现蓝图

**交互式确认**：Phase 11 完成后必须向用户展示架构方案并获取确认，再进入 Phase 12。
