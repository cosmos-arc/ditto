# Ditto 工具链长期方向评估

日期：2026-09-06。仓库基线：`2e8b8818634275a4eba60b460d01434966ab5b15`。

后续状态：维护者已确认 Python 迁移到 uv、JS 保留 Bun 并整改现有工具链问题。实施范围和验收以 [迁移 Python 到 uv，保留 Bun 并修复工具链执行一致性](https://github.com/cosmos-arc/ditto/issues/101) 为准；本报告保留研究过程，代码迁移尚未执行。

本报告排除迁移工作量、现有投入和团队学习成本；保留持续安装/执行效率、长期复杂度、失败面、兼容性与可复现性作为架构判断维度。结论是研究建议，尚未取代现行 ADR。

用户补充：最早选择 Bun，是因为当时效率显著优于 pnpm。这是用户提供的历史体验，不是本轮的新基准测量。它提醒本评估不能把持续效率收益与应排除的迁移成本混为一谈；以下综合建议据此校准，独立研究报告保留原始结论与证据。

## 结论

**对当前 Ditto，建议 Python 包/项目管理采用 uv workspace；Web 保留 Bun 包管理，并显式固定工具实际使用的 Node LTS。当前没有充分的系统理由要求换成 pnpm；pnpm 是出现具体治理缺口时再选择的备选。** 保留 Bun 的理由是它已满足当前主要需求，且存在用户报告的效率收益；不是迁移工作量大，也不是断言今天任何场景 Bun 都更快。

| 决策 | 建议 | 判断依据 |
| --- | --- | --- |
| Python 包、依赖图、虚拟环境 | uv workspace + 一个 `uv.lock` | 当前是 13 个相互关联的 Python distribution；本地包元数据已经存在，尚未发现必须由 Conda 管理的业务原生工具链 |
| JS 包管理 | 保留 Bun + 一个 `bun.lock` | 当前已有隔离安装、冻结锁与显式脚本信任政策；持续效率是有效收益，尚无证据证明 pnpm 的额外政策能力为本仓必需 |
| JS 工具运行时 | 显式固定受工具支持的 Node LTS 版本 | 当前 Vite/Vitest/Playwright/dependency-cruiser 工具链已经使用 Node，同时也直接使用 Bun；Node 未进入现有版本检查 |
| 跨栈任务图 | 保留一个根任务图；退出 Pixi 时由轻量 runner 承接 | `uv run` 与 `pnpm run` 都不能自动保全现有跨栈任务依赖关系 |
| 原生运行环境与制品 | 明确 OS、解释器、原生库/二进制来源及制品 digest | Python/JS lockfile 不等于整个计算环境，不足以单独证明数值行为或二进制重建一致 |

这不是“业界只有一套正确答案”。官方资料能证明能力和边界；上述优先级是根据 Ditto 的产品形态作出的工程判断。

## Python：为什么更倾向 uv

Ditto 的 13 个包各有 `pyproject.toml`，根 Pixi 再列举 editable 包路径并维护主要依赖范围；还有专门的 package-contract 检查，校验发现的叶包、根列表、lock 与依赖约束之间的一致性。这说明项目确实需要一个清楚的 Python workspace 模型。[仓库包声明](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/pixi.toml#L53)、[一致性检查](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/tooling/quality/package_contracts.py#L281)

uv workspace 原生表达“多个相互关联的 Python 项目，共享解析与 lockfile”，允许按成员运行和同步，贴合这里的模块化单体。采用它可以让 Python 包元数据更直接地成为安装依赖图的输入；产品版本、架构边界和发布 cohort 等仓库特有规则仍应保留。[uv workspace 官方说明](https://docs.astral.sh/uv/concepts/projects/workspaces/)

Pixi 本身已经使用 uv 库处理 PyPI 依赖。这里倾向 uv，是倾向在当前需求下采用单一 Python 包求解体系，减少 Conda 与 PyPI 两阶段协调；不是假定 Pixi 缺少快速 resolver。[Pixi 的 Conda/PyPI 求解流程](https://pixi.prefix.dev/latest/concepts/conda_pypi/)

根 Pixi 直接声明的 Conda 项目前为 Python 及 Python 库，没有显式 CUDA、GDAL、FFmpeg 或自定义编译器需求。CVXPY、SciPy 和求解器已有 PyPI wheel 锁定记录。因此，“量化/科学计算”这一分类本身不能推出必须使用 Conda。[运行依赖](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/pixi.toml#L22)、[组合优化依赖](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/packages/portfolio/pyproject.toml#L6)

但项目并非没有原生依赖。当前 Conda 闭包确实含 BLAS/LAPACK、Lua/LuaJIT、Graphviz 等；wheel 是否提供对应功能、CPU/OS 基线是否合适、底层数值实现是否改变，必须分别验证。已检查的 NumPy、Polars、DuckDB 与 Lupa 锁定版本存在三目标平台可用的 CPython 3.13 wheel；这只排除了这些包的明显分发障碍，不等于全部依赖与产品功能已通过 uv 验收。版本和文件证据见 [Python 专项研究](2026-09-06-python-toolchain-pixi-uv.md)。

推荐 uv 也不依赖以下错误前提：

- 不把当前根声明与叶包声明一概视为坏重复。叶包的直接依赖与应用整体的版本政策本来是不同职责。
- 不宣称 Pixi 无法使用标准 Python 元数据。uv 的优势是项目模型在本仓的适配度，并非标准的独占权。
- 不宣称 uv workspace 自动实现 Python 包之间的导入隔离。官方明确说明一个成员仍可能导入另一成员带入环境的依赖，因此 import-linter 等边界检查仍然必要。[uv workspace 限制](https://docs.astral.sh/uv/concepts/projects/workspaces/#when-not-to-use-workspaces)
- 不把 `uv.lock` 称为 Python 标准锁格式。它是 uv 管理的格式；标准化的 `pylock.toml` 是另一种导出/互操作格式。[uv 项目文件](https://docs.astral.sh/uv/concepts/projects/layout/#relationship-to-pylocktoml)

**保留 Pixi 的最强理由**是要求同一个环境模型统一管理 Python 与独立原生软件、ABI 及跨语言工具，并利用它的任务执行能力。如果这些成为经确认的产品要求，Pixi 仍可能是更好的长期选择；不应为了让依赖清单看起来“更 Python”而拆散真实环境责任。

即使排除迁移成本，uv 加独立 runner 也会产生长期的版本、环境激活与调度衔接责任。不能把“分成专职工具”本身当成更简单的证明；本次偏好来自已观察到的 Python 项目需求，而不是职责分离的教条。

## JavaScript：pnpm 的建议为何较弱

当前 Bun 已采用 isolated linker、空 hoist 配置、显式信任列表和单一锁文件。产品构建是 Vite/TypeScript，常规单元测试是 Vitest，界面是浏览器中的 React SPA；没有 Bun 产品服务端。[Bun 配置](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/bunfig.toml#L1)、[根 manifest](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/package.json#L6)、[Web scripts](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/apps/web/package.json#L7)

因此，不能用“Bun 依赖扁平、只有 pnpm 能约束幽灵依赖”作为迁移理由。Bun 官方已提供 pnpm 风格的隔离安装，两者也都不是阻止所有未声明导入的安全沙箱。[Bun isolated installs](https://bun.com/docs/pm/isolated-installs)

更具体的系统问题是：Node 已被 setup 脚本、dependency-cruiser loader 和测试使用，但现有 toolchain 检查只列 Bun、Pixi、Python。另一方面，仓库又直接用 Bun 执行 Vite/Playwright CLI、脚本及少量 `bun:test`。这形成了两种 JS 运行时的实际职责，却没有把 Node 版本纳入同等明确的环境合同。[Node 调用](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/.github/actions/setup-bun/action.yml#L16)、[版本检查](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/tooling/dev/toolchain.py#L70)、[系统验收启动](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/tooling/dev/system_tests.py#L164)

还要区分 `bun run` 与 Bun runtime：Bun 默认尊重工具入口的 Node shebang，不能从命令前缀推断所有 CLI 都运行在 Bun；直接执行某个 JS 文件和使用 `--bun` 又是不同路径。专项研究按这些路径分别核查。[Bun runtime 官方说明](https://bun.com/docs/runtime)

**pnpm + Node LTS 是可行方案，但统一工具运行时并不要求换掉 Bun 包管理。** pnpm 提供完整 workspace 与安装政策设置；这些额外控制项只有对应具体需求才产生收益。当前更明确的工作是将 Node 纳入工具链合同；具体补丁版本还必须同时满足 Vite/Vitest/Playwright 和 loader API 的要求。[pnpm 设置](https://pnpm.io/settings)、[Node 发布与支持周期](https://nodejs.org/en/about/previous-releases)

**如果只替换 PM，继续保留 Bun 脚本、Bun 测试和 Node，结论是没有充分必要性。** Bun PM 配合固定的 Node 是本报告校准后的建议。Bun 官方明确包管理器可独立用于 Node 项目，安装性能与脚本运行时是可以分开选择的维度。用户报告的历史效率优势进一步支持不要仅因 pnpm 的治理选项更多就替换；当前性能优势的幅度仍需同仓库、同锁定语义和冷/热缓存条件下的测量才能确定，本轮未运行这些测试。[Bun install](https://bun.com/docs/pm/cli/install)

当前 pnpm 官方站点为 12.x，Bun 仓库固定为 1.3.14；供应链默认值会随版本改变，不能把旧教程的默认值当作今日事实。安全与兼容细节见 [JavaScript 专项研究](2026-09-06-js-toolchain-bun-pnpm.md)。

## 不可遗漏的任务图与发布语义

现有 Pixi 根有 61 个任务、12 个带依赖关系的组合任务，覆盖 Python、Web、契约、系统验收、安全和制品。单一跨栈任务入口有明确价值；包管理器替换不应导致本地与 CI 各自维护一套执行顺序。[Pixi 根任务](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/pixi.toml#L155)

uv 的 `run` 负责在项目环境执行命令，并不是现有 `depends-on` 图的替代物。若选择退出 Pixi，建议用一个轻量、跨平台的根 runner 承接，继续复用现有叶子脚本，不重写调度框架。Task 是已核实支持任务依赖和 Windows 安装的候选；它的依赖默认并行，不能把现有任务列表机械搬入 `deps`，必须保留前后置关系与资源约束。本轮未评测全部 runner，因此不把 Task 唯一化。[uv run](https://docs.astral.sh/uv/concepts/projects/run/)、[Task 依赖语义](https://taskfile.dev/docs/guide#task-dependencies)、[Task 安装](https://taskfile.dev/docs/installation)

长期正确性还要求保留以下结果，而非保留特定文件名：

1. **声明与锁一致。** uv 的 `--locked` 在锁过期时失败；`--frozen` 跳过锁新鲜度检查，不能机械等同于另一工具的 frozen 模式。dev 与 production 应从同一解析结果选取对应依赖集合，并验证实际安装的闭包。[uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
2. **环境身份完整。** 当前制品已记录环境锁 hash 和基础镜像 digest。更换工具后仍要记录解释器、目标平台、OS/原生库、Python/JS lock 与制品身份；不能只将 `pixi.lock` hash 改为 `uv.lock` hash 就宣布保真。[Docker 发布环境](https://github.com/cosmos-arc/ditto/blob/2e8b8818634275a4eba60b460d01434966ab5b15/deploy/docker/Dockerfile#L2)
3. **数值行为显式验证。** 同一版本号、同一 lockfile 或成功安装均不代表不同 OS、BLAS、CPU 与求解器输出逐位相同。当前 Pixi lock 本身也包含平台间不同的 NumPy/Polars/DuckDB 版本。应区分依赖可重建与计算结果的误差/业务合同。
4. **联邦式 monorepo 继续成立。** Python 和 Web 独立产物、同提交验收、OpenAPI 契约和 release cohort 不需要随包管理器改变。没有当前需求支持仅为这次替换引入 Nx/Bazel/Pants 一类更大的控制面。

## 对现行 ADR 的影响

[ADR 0001](../adr/0001-project-stack-selection.md) 用科学计算库的 Conda 需求解释 Pixi 选择；本次研究认为该理由应以具体包、功能和平台证据重新验证。[ADR 0010](../adr/0010-polyglot-monorepo.md) 第 3 节明确规定 Pixi 根图与 Bun workspace；若采纳本报告，需要重新决策这些工具所有权条款，同时保留单一任务图、独立产物、契约与 cohort 原则。

本轮未修改上述 ADR，也没有将研究偏好表述为维护者已采纳的决定。

## 证据范围与 wayfinder

已完成仓库 manifest、lock、CI、Docker、运行脚本和检查器的静态审计，以及官方文档/公开包元数据调查。没有执行 uv/pnpm 安装、迁移、基准测试或三平台产品验收；本文支持方向判断，不是迁移验收证明。

Canonical 地图：[Ditto 工具链长期方向：Pixi/uv 与 Bun/pnpm](https://github.com/cosmos-arc/ditto/issues/97)。详细研究结论分别记录于 [Python 包管理与原生环境：Pixi 和 uv 的长期适配](https://github.com/cosmos-arc/ditto/issues/98) 和 [Web 包管理与运行时：Bun 和 pnpm/Node 的长期适配](https://github.com/cosmos-arc/ditto/issues/99)。维护者确认后的最终取舍记录在 [采纳 Ditto 长期工具链的职责分工](https://github.com/cosmos-arc/ditto/issues/100)；地图与决定票已完成，后续由 [实施规格](https://github.com/cosmos-arc/ditto/issues/101) 承载。
