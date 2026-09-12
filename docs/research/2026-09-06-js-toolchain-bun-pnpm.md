# Ditto Web 工具链：Bun 与 pnpm / Node 的长期方向

研究日期：2026-09-06。研究票：[Web 包管理与运行时：Bun 和 pnpm/Node 的长期适配](https://github.com/cosmos-arc/ditto/issues/99)。仓库基线：`2e8b8818634275a4eba60b460d01434966ab5b15`。只评价长期系统适配，不计迁移成本；未安装依赖、修改配置或执行迁移。

结论：**忽略迁移成本，我倾向以 pnpm 管理 Web 依赖，以明确锁定的 Node LTS 运行 Web 工具和仓库脚本。Node 显式治理的推荐强度高；Bun 包管理换成 pnpm 的推荐强度中等，并非现有 Bun 方案在原则上错误。** 两项决策必须分开。仅把 `bun install` 换成 `pnpm install`，不会自动消除 Bun API、Bun 测试运行器或隐式 Node。

## 当前系统实际使用了什么

以下路径均相对上述仓库基线，行号用于复核：

| 仓库证据 | 对评价的影响 |
| --- | --- |
| `package.json:6` 固定 `bun@1.3.14`；`:7` 只有 `apps/web` 一个 JS workspace | 不是需要几十个 JS 包协同发布的大型 JS monorepo，不能靠假设未来规模为 pnpm 辩护 |
| `bunfig.toml:2` 为 `isolated`，`:4`、`:5` 两个 hoist pattern 均为空 | 当前 Bun 已主动限制依赖提升，不能以“Bun 默认扁平安装”批评现状 |
| `package.json:10` 为 `trustedDependencies: []`，`tooling/release/tests/test_repository_policy.py:213` 起有对应仓库约束 | 已有明确的依赖安装脚本禁用策略 |
| `pixi.toml:224` 和 `.github/workflows/ci.yml:166` 使用冻结安装 | 现有流程已管理 lockfile，不存在“必须换 pnpm 才能可复现”的理由 |
| `.github/renovate.json:22` 配置 `minimumReleaseAge: "7 days"` | 更新机器人已有冷静期；不能等同于包管理器覆盖手工解析和所有锁条目的策略 |
| `apps/web/package.json:7`、`:14`、`:16` 使用 Vite / Vitest；`:90` 为 Vite 8，`:91` 为 Vitest 4.1.2；根 `package.json:20` 为 Playwright 1.62.1 | Bun 内置 bundler / test runner 并未取代主要 Web 工具 |
| `apps/web/package.json:8`、`:19`、`:21` 等脚本显式调用 Bun；`tooling/quality/tests/frontend_architecture.test.mjs:1`、`frontend_color_policy.test.mjs:1` 导入 `bun:test` | Bun 确实还承担脚本运行时和少量测试运行器，不能把迁移描述为换 lockfile |
| `apps/web/scripts/capture-prototype-baseline.mjs:103` 使用 `Bun.spawnSync`，`:247` 使用 `Bun.$` | 存在 Bun 专属 API，运行时选择有真实影响 |
| `.github/actions/setup-bun/action.yml:16` 调用 `node`；`apps/web/scripts/dependency-cruiser-typescript-loader.mjs:1` 导入 `registerHooks`；对应测试 `:7` 显式 spawn `node` | Node 已经是运行依赖，并非改用 pnpm 后才新增 |
| `tooling/dev/toolchain.py:70` 起仅校验 Bun、Pixi、Python | 当前最具体的治理缺口是 Node 没进入同一显式工具链契约 |

## 同一时代的能力比较

仓库固定 Bun 1.3.14；Bun 对照采用查阅当日官方在线文档，文档可能包含后续版本能力，不能把全部现行能力倒推成 1.3.14 已验证行为。pnpm 官方文档当前为 **12.x**，官方最新稳定发布页为 [pnpm 12.3.4](https://github.com/pnpm/pnpm/releases/tag/v12.3.4)，发布于 2026-09-04。这里只比较能力方向，不建议不经验证就追踪 latest。

| 维度 | Bun | pnpm | 对 Ditto 的判断 |
| --- | --- | --- | --- |
| 安装结构 | 支持 isolated store、symlink、按 peer 集合区分实例 | 默认 isolated，也支持其他 linker | 两者都有必要能力；现有 Bun 已选择正确模式 |
| Phantom dependencies | 可以关闭隐藏 hoist；根 `node_modules` 的祖先可见性仍存在 | 默认隐藏 hoist 开启，属于 semistrict；也可关闭 | pnpm 默认并不比当前 Bun 的空 hoist patterns 更严格；两者都需要源代码依赖边界检查 |
| Workspace、catalog、peer | 有 workspace、catalog，以及 isolated peer resolution | 有 workspace 协议、catalog、peer 策略、workspace 注入等 | pnpm 的策略控制更细，但当前单 SPA 不靠复杂 workspace 功能获益 |
| Lock 与 CI | 文本 `bun.lock`；显式冻结命令可约束有锁时的解析 | `pnpm-lock.yaml`；CI 有锁时默认冻结；显式冻结会拒绝缺锁 | 两者可形成可复现依赖流程，仍需锁定运行时和 OS / 浏览器等输入 |
| 依赖构建脚本 | 内置信任名单；显式空 `trustedDependencies` 会替换名单并禁用全部依赖脚本 | 未审查构建默认拒绝，`allowBuilds` 明确允许 / 拒绝，可限定版本或具体来源 | 当前 Bun 已安全收紧；pnpm 更擅长把“明确拒绝”和“尚未审查”作为不同状态管理 |
| 新版本与来源策略 | 支持 release age；只管新解析，缺发布时间视为通过 | 支持 release age、来源限制、信任不得降级、锁条目策略复核 | pnpm 在集中表达供应链规则上更完整；规则仍须显式配置，不能把产品名称当作安全保证 |
| 运行时 | Bun 是运行时，也可仅用其包管理器运行 Node CLI | pnpm 以包管理为核心，也能声明、下载并锁定 Node / Bun / Deno | 包管理器与运行时可以独立选择；没有“用 pnpm 就必须放弃 Bun”的技术约束 |

安装结构与边界来源：[Bun isolated installs](https://bun.com/docs/pm/isolated-installs)、[pnpm node_modules 与 hoisting](https://pnpm.io/settings/node-modules)。Bun 文档明确提示根依赖仍可沿祖先目录解析；isolated 不是安全沙箱。仓库已有 `apps/web/scripts/check-leaf-dependencies.ts:46` 起基于叶包 manifest 的检查，不能因更换包管理器而移除。

Workspace / peer 来源：[Bun workspaces](https://bun.com/docs/pm/workspaces)、[pnpm workspaces](https://pnpm.io/workspaces)、[pnpm catalogs](https://pnpm.io/catalogs)、[pnpm peer settings](https://pnpm.io/settings/peer-dependencies)。pnpm 的 `strictPeerDependencies` 默认仍为 false；需要缺失或不兼容 peer 失败时必须显式启用。Catalog 统一声明范围，不代表本身就保证整个传递依赖图只有一个版本。

锁与冻结来源：[Bun install](https://bun.com/docs/pm/cli/install)、[pnpm install](https://pnpm.io/cli/install)。当前 Bun 文档特别说明：未提供 lockfile 时，`--frozen-lockfile` 可以按 manifest 安装而不写锁；仓库已检查 `bun.lock` 存在（`tooling/release/tests/test_repository_policy.py:228`），这一点应视为流程约束。冻结安装约束依赖解析，不证明可重现构建产物的字节完全一致。

构建脚本来源：[Bun lifecycle scripts](https://bun.com/docs/pm/lifecycle)、[pnpm build settings](https://pnpm.io/settings/build)。pnpm 12.x 使用 `allowBuilds`，`strictDepBuilds` 默认 true；`onlyBuiltDependencies`、`ignoredBuiltDependencies` 等旧设置在 v11 已移除。不能引用 pnpm 10 的配置样例作为当前方案。

供应链来源：[Bun release age](https://bun.com/docs/pm/cli/install#minimum-release-age)、[pnpm dependency resolution](https://pnpm.io/settings/dependency-resolution)。pnpm 默认 1440 分钟但不严格，无合格版本可回退；明确配置阈值才默认严格，缺发布时间默认仍跳过。需要 fail closed 时应明确拒绝缺时间，并选择信任策略。`trustPolicy` 默认 off；`trustLockfile` 默认 false，会重验锁条目的策略。Bun 的 age gate 不重新检查既有锁条目。以上均只是降低暴露风险，不证明包无恶意。

## 为什么 Node LTS 比“换包管理器”更有决定性

**先区分命令入口和实际运行时。** Bun 官方说明 `bun run` 默认尊重 CLI 的 Node shebang；`bun run --bun vite` 才强制使用 Bun。因此，仓库的 `bun run dev` 或 `bun run test:unit` 不能直接作为 Vite / Vitest 在 Bun runtime 运行的证据。直接 `bun scripts/foo.mjs`、`Bun.*` 和 `bun:test` 则是不同路径。[Bun runtime：--bun](https://bun.com/docs/runtime#bun)

官方工具要求提供了比“兼容 Node”自我声明更有用的默认选择依据：

- Vite 当前指南要求 Node 20.19+ / 22.12+，同时提供 Bun 包管理命令；这证明 Bun 安装入口受文档覆盖，不意味着每一项 Bun runtime 行为受上游保证。[Vite guide](https://vite.dev/guide/)
- 仓库 Vitest 4 对应的版本化文档要求 Node >=20、Vite >=6；不能误用当前已指向 Vitest 5 的首页要求来描述仓库 Vitest 4。[Vitest 4 guide](https://v4.vitest.dev/guide/)
- Playwright 当前系统要求列出 Node 最新 22.x / 24.x / 26.x，未把 Bun 列为该处运行时要求。[Playwright installation](https://playwright.dev/docs/intro#system-requirements)
- 现有 loader 使用的 `module.registerHooks` 从 Node 22.15 / 23.5 才加入；仅满足 Vite 的最低版本不保证满足本仓库脚本。[Node module API](https://nodejs.org/api/module.html#moduleregisterhooksoptions)

推论：以工具上游明确列出的 Node 为默认运行时，可以让构建、覆盖率、loader、测试工具的支持预期更一致，且避免无产品需求时长期维护两套脚本运行语义。Bun 官方自己也列出部分 Node API 的支持缺口；这不是证明当前工具必然失败，而是不能用“兼容 Node”四个字替代对具体工具组合的验证。[Bun Node compatibility](https://bun.com/docs/runtime/nodejs-compat)

Node 的官方发布策略有明确 LTS 阶段和通常约 30 个月关键修复保障；查阅当日 Node 22 / 24 为 LTS，26 为 Current，20 已 EOL。因此可选范围应为仍受支持、满足工具最低要求的 LTS，并把具体版本纳入本地与 CI 契约，不能只写“Node >=20”。本研究不选定精确补丁版本。[Node release policy](https://nodejs.org/en/about/previous-releases)

实现这项治理不强制要求 pnpm。保留 Bun 包管理器、显式锁定 Node 也成立。pnpm 则提供 `devEngines.runtime`，可将运行时精确版本及 checksum 纳入 lockfile、让脚本使用本地运行时，且支持包括 Bun 在内的多个 runtime；这恰好说明包管理与 runtime 是两个可组合的维度。[pnpm package.json](https://pnpm.io/package_json#devenginesruntime)

## 最强反方理由与改变判断的条件

保留 Bun 的最强理由不是迁移很贵，而是它已经满足这个单 SPA 的核心包管理需要：isolated、冻结锁、显式拒绝依赖脚本、workspace 和 catalog 都存在。若显式治理 Node，并把需要的供应链策略补到一致的安装入口，**Bun + Node LTS 同样是合理系统设计**。不能为了 pnpm 的选项多而引入暂时用不上的治理复杂度。

我仍偏向 pnpm + Node LTS：Ditto 的主要 JS 工具并没有选用 Bun 内置替代品，pnpm 可把依赖政策和 runtime pin 清晰记录为仓库数据，Node 则对应上游工具明确描述的运行基线。这个理由来自当前角色适配和规则可验证性，既不是流行度排序，也不是宣称 Bun 不成熟。

以下证据会改变结论：

- 若产品明确选择 Bun 原生服务、`Bun.serve` / Bun 原生能力或单二进制交付，并以它作为受支持生产 runtime，一体化 Bun 工具链的价值会显著上升。本仓库目前的脚本便利不等于这种产品需求。
- 若保留 Bun、固定 Node、集中供应链策略后，真实 CI 表明所有需要的治理和兼容要求已满足，则“必须换 pnpm”的结论不成立。
- 若未来出现多个独立 JS 包及多套 peer consumer、发布、部署裁剪需求，pnpm 的进一步策略能力将更有直接价值；本次不以这个未来假设计分。
- 若目标是彻底移除 Node，需要上游工具对 Bun 的支持声明以及仓库完整构建、Vitest 覆盖率、Playwright、loader 的实际验证；安装成功或普通测试通过不足以证明全部路径等价。

## 决策边界

方向已可判断，无须为此先做迁移实验：**推荐目标是 pnpm 管依赖、Node LTS 管运行；Node 显式治理是必要约束，pnpm 替换是合理偏好。** 若以后执行，验收应复用现有构建、类型、单元 / 覆盖率、架构脚本、浏览器测试和契约生成检查，并覆盖已识别的 Bun 专属路径，而不是另造一套泛化 benchmark。此次只做源码 / 配置和官方资料研究，没有宣称运行时迁移已验证。
