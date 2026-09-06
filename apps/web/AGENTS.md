# Ditto Web Agent Guide

React SPA 消费同仓 FastAPI 的本地 OpenAPI 契约。Web 依赖和叶子任务由 Bun 管理，跨栈验证从根 Pixi 入口执行。

## 按任务读取

- 产品方向或范围：[PRODUCT.md](PRODUCT.md)、[产品 brief](docs/brief/product-brief.md) 与 [约束](docs/brief/constitution.md)。
- 页面、导航、状态或原型：[设计入口](DESIGN.md)、[产品 IA](docs/designs/specs/01_product_information_architecture.md)、[页面蓝图](docs/designs/specs/02_core_page_blueprints.md) 与 [交互状态](docs/designs/specs/04_interaction_state_spec.md)。
- 布局、selector 或合同生成：[页面合同](docs/contracts/README.md) 与目标页面 JSON。
- 组件归属或依赖：[前端架构](docs/engineering/frontend-architecture.md)。
- 行为与视觉验证：[Web 测试说明](docs/engineering/testing.md)；跨栈/API 变化另读 [契约指南](../../contracts/AGENTS.md)。
- 宿主配置：[根 Harness](../../docs/engineering/agent-harness.md)。

## 不变量

- 当前源码、类型与机器依赖图定义行为；历史计划、manifest 和原型不能覆盖当前实现。
- 生产 TypeScript strict；API path/method/params/body/response 由 generated paths 推导，generated DTO 经 feature adapter 转为 view model。
- 服务端状态用 TanStack Query，跨页面客户端偏好用 Zustand，局部 UI 状态保持局部。
- 跨 feature 工作流归 workflows，消费 feature public API；components/ui 与 lib 不依赖 feature，深层依赖须遵守机器边界。
- 静态视觉值来自 Design Token；inline style 限数据驱动几何。原型字面值低于设计系统事实。
- 数据界面覆盖 loading、empty、error、stale；键盘操作、focus、风险表达与破坏性操作确认必须有效。
- route tree 与合同产物通过既有 generator 更新。Biome 和类型配置是静态规则事实源，不扩大 ignore 或放宽类型绕过失败。

验证按实际影响选择目标测试、类型、合同及浏览器证据；普通 UI 调整无需重建整套原型/合同生命周期。授权与工作树边界沿用根指南。
