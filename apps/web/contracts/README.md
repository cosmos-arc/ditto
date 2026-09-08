# 页面合同与视觉验证

页面 JSON 是 selector、状态、响应式与视觉阈值的事实源；React shell 和视觉配置是生成消费者。只有布局或交互合同实际变化时才更新相关 JSON，普通 UI 修复不要求创建原型 edition 或重复全生命周期。

## 工具入口

以下命令从 Web workspace 执行：

- `bun run generate-contracts`：从全部页面 JSON 生成 shell 与视觉配置。
- `bun scripts/page-contract/create.mjs --prototype <html>`：采集原型 DOM 与度量，按目标页面更新合同。
- `bun run prototype:gates -- --prototype <html>`：检查目标原型；可传 `--viewport NAME=WIDTHxHEIGHT` 指定视口。
- `bun run visual:audit:cli --help`：显示 React/原型服务地址、路由、输出及视觉比较参数。

validator 的公开接口位于 `scripts/page-contract/validators/contract-validator.mjs`：`validateContract(contract, {root})` 与 `validateAllContracts({root, contractsDir})`。这里 root 是 Web workspace，contractsDir 是其下的页面合同目录；脚本使用者将 `passed`/`allPassed` 的 false 映射为非零退出码。

## 合同变更

- shellFamily、pagePattern、slot 及状态词汇以现有 schema 与生成配置为准。页面蓝图、路由和状态说明引用同一事实，不另存枚举计数。
- required shell slot 使用稳定 selector；明确 loading、empty、error、stale，以及必要的可访问性与 compact 行为。
- 零容忍阈值保持为零；修复失败原因，不通过提升 status 或放宽阈值消除错误。
- 改变 selector、度量或阈值后更新版本与受影响消费者，运行目标合同/视觉测试并重新生成。产品范围变化仍由用户决定。
- 原型中合同 slot 位于有效 shell 下。视口、字体、主题、密度、数据和服务状态一致时再比较截图，记录有依据的设计系统偏离。

视觉审查关注实际信息层级、交互、可访问性和数据表达；无需固定评审人数、主观分数或隐式提交/tag。无法测量的结果直接标注。
