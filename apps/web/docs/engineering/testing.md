# Web 测试

风险和证据原则见 [根测试指南](../../../../docs/engineering/testing.md)。React Testing Library 通过角色、标签、可见文案与用户事件观察行为；MSW 表达网络边界，避免仅断言内部调用次数。

## 入口与环境

从 Web workspace 执行 `bun run test:unit` 验证 src 单元行为，`bun run test:coverage` 同时生成覆盖证据，`bun run test:prototype` 验证 scripts 下的原型、视觉和工具合同。覆盖阈值以 `vitest.config.ts` 为准，保留独立的高风险分支阈值。

从仓库根执行 `task check-web` 做日常 Web 验证，`task web-ci` 做 Web 完整验证，`task test-system` 验证 production Web 与隔离 API。Bun 不再有独立 check/ci 编排。

首次运行浏览器测试时，在实际调用 Playwright 的 workspace 用锁定依赖执行 `bunx playwright install chromium`。浏览器缓存可通过 PLAYWRIGHT_BROWSERS_PATH 隔离；环境准备失败不代表产品断言失败。类型、coverage 和 build 的现有入口会生成 route tree，不手写生成文件。

## 视觉与合同

工具和操作说明见 [页面合同](../../contracts/README.md)。按实际影响检查对应路由、交互、可访问性、主题/密度与视口；普通局部改动不运行完整原型生命周期。

视觉不稳定先核对服务、字体、数据、viewport 和 selector；集中超时先排查资源争用，不直接增加 timeout 或重试。测试只收集真实工程工具，Claude skill 镜像不重复运行。

普通 `web-product-check` 只执行实际路由覆盖检查。原型 freeze、完成看板和 `audit:product-recovery` 保留为显式历史审计，不进入普通 UI 的必经验证。
