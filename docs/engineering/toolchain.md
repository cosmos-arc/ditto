# 开发与发布工具链

Task 是根任务图；uv 管理 13 个 Python distribution；Bun 保留 Web 安装与专用 API，Node 执行 Node CLI。版本声明分别在 `.task-version`、`pyproject.toml` 的 `tool.uv.required-version`、`.python-version`、`package.json` 的 `packageManager` 和 `.node-version`。uv 为范围声明 `>=0.12.7,<0.13`：下界由 Renovate 跟进，上界是主版本闸门（uv 0.13 发布时人工评估抬升）；本机任意满足范围的 uv（含 Homebrew 安装）均可工作，`.cache/toolchains/bin` 保留 0.12.7 精确入口；CI 经 setup-uv 的 `resolution-strategy: highest` 在范围内取最高版；Docker 构建镜像继续按 digest 固定。

## 准备与只读检查

工具来源为 [uv release](https://github.com/astral-sh/uv/releases/tag/0.12.7)、[Task release](https://github.com/go-task/task/releases/tag/v3.53.1)、[Node 官方归档](https://nodejs.org/dist/v24.20.0/) 和 [Bun release](https://github.com/oven-sh/bun/releases/tag/bun-v1.3.14)。使用对应平台归档及发布校验和安装声明版本，再将可执行文件加入 PATH。CI 的 `setup-toolchain` action 从相同声明安装。

```bash
task bootstrap                 # uv locked sync、Bun frozen install、oasdiff 准备
task browser-install           # 已安装 Playwright 的 Chromium 资产
task dev
task check
task type -- --tests
task test -- --fast
uv run --no-sync pytest path/to/test.py -q -n 0
```

普通验证使用 `uv lock --check --offline` 和 `uv sync --check --locked --offline --all-packages`。后续命令使用 `uv run --no-sync`，缺环境、锁漂移或缺包均失败，不自动同步。Bun 检查比 frozen 安装多一步：比较根与 Web manifest、锁中的 workspace 声明及已安装直接依赖的精确版本。Node CLI 通过预加载检查固定运行时与准备状态；没有 bunx/npx 下载回退。

Bun 安装显式指定 npmjs registry，避免宿主 `.npmrc` 镜像覆盖仓库配置；保留 isolated、空提升、空 `trustedDependencies`。只有显式安装流程下载依赖和浏览器。Ruff hook 直接调用本 worktree `.venv` 中已安装的工具；Stop 不查询版本、运行项目工具或写收据。

Task 的组合任务顺序调用前置任务，失败立即传播；构建完成后才能消费其输出。验证没有结果缓存。`.venv`、`.cache` 和构建输出属于各自 worktree；uv/Bun 下载缓存和校验后的 oasdiff 归档可共享。

## Python 迁移记录

基线为提交 `2e8b8818634275a4eba60b460d01434966ab5b15` 的 `pixi.lock`。包级映射见 [toolchain-package-mapping.csv](toolchain-package-mapping.csv)：记录平台、原包名/版本、来源和新 PyPI 分发版本。首次求解以原锁约束种子，随后删除种子；已验证所有解析版本与平台 marker 保留，维护时无需更新第二份版本约束。

唯一已确认的必要运行时版本调整：macOS 的 Conda Prefect 3.8.1 对应 PyPI 分发要求 FastAPI ≥0.139，与项目 <0.137 冲突，因此采用原 Linux/Windows 已锁定的 Prefect 3.6.24。原锁的 `pydantic-extra-types==2.11.2` 已被 PyPI 撤回（非安全原因）；本次保留，后续依赖更新单独审查。

开发解释器使用固定 uv 版本所分发的 python-build-standalone CPython 3.13.14；项目只接受 uv managed Python。生产容器在固定 digest 的 distroless Debian 13 base 上运行 CPython 3.13.14，并把构建阶段的 uv、pip 和源码 checkout 排除在最终镜像外；显式禁止解释器下载。两者来源不同，不能仅凭同一 Python 版本宣称原生 ABI 相同。

Conda 的 NumPy/BLAS、DuckDB、Polars、Lupa 由 PyPI wheel 提供；Windows 原 MKL 与新 wheel 的数学库差异通过原有数值容差验证。Conda 引入的 Lua、Graphviz/GTK 等系统组件不作为独立 Python 依赖复制；实际 Prefect 内存队列的 Lua 能力由 Lupa wheel 验收。`no-build` 禁止第三方源码编译；本地 setuptools 包正常构建。支持范围保持 Linux x86_64、macOS ARM64、Windows x64，锁定解析不替代各平台的真实执行证据。

```bash
# 显式准备独立生产环境，不修改开发 .venv
UV_PROJECT_ENVIRONMENT="$PWD/.cache/production-venv" \
  uv sync --locked --all-packages --no-dev --no-editable
```

生产容器仅复制非 editable 环境、固定 Python 运行时、必要系统库与配置，不复制源码 checkout、uv 或 Bun。当前发布按 [.github/workflows/release.yml](../../.github/workflows/release.yml) 和 [artifact gate](../../tooling/release/artifact_gate.py) 验证镜像/Web 制品身份、扫描对象、SPDX SBOM 绑定与 checksum。环境摘要的输入由 [environment_identity.py](../../tooling/release/environment_identity.py) 定义。

release-cohort 注册链、copied-library source provenance SPDX、release inputs 和 bundle stdlib verifier 已退役，历史 cohort 与其自带 verifier 保留原提交语境。活跃的 [Web/API 兼容策略](../../contracts/openapi/README.md) 仍校验 allowlist 字节身份，要求精确匹配并拒绝隐式兼容。

## CI 时长基线

通过 run [34100716341](https://github.com/cosmos-arc/ditto/actions/runs/34100716341) 中，`Backend tests and coverage` 约 31 分 44 秒，整轮 CI 约 33 分 18 秒；16,501 个测试通过、74 个跳过。最慢的真实测试组为 scheduler capacity `[2]` 345.70 秒、capacity `[4]` 300.20 秒和 128-candidate backend e2e wrapper 303.20 秒。它们在 job 内并发，但合计占据主要窗口；这不是 public repo quota、`TUSHARE_TOKEN` 或 release scanner 造成的。release 扫描共享 Trivy DB volume，避免最终镜像与来源镜像扫描重复下载漏洞库。

2026-09-12 的排队/执行分解结论（15 个 PR runs）：排队中位数约 3 秒，full 门执行中位数
16.4 分钟（分片后 backend-shards ~14 分钟为关键路径，后置阶段串行叠加），docs 类 0.4
分钟；详见 [PR 验证时长诊断](../research/2026-09-12-pr-duration-diagnosis.md)。


### 2026-09-08 有限反馈诊断

迁移后的样本不能与上述单 job 旧基线直接比较。以下时间来自 Actions 的 run/job/step
时间戳，包含对应层级的调度与收尾，不等同单项测试耗时。

| 样本 | 整轮 | 后端分片 2 / 3 | macOS gate job |
| --- | ---: | ---: | ---: |
| [#110 PR，34202493420](https://github.com/cosmos-arc/ditto/actions/runs/34202493420)，扫描误报及宿主修复 | 16m25s | 13m21s / 13m39s | 13m24s |
| [main，34232894885](https://github.com/cosmos-arc/ditto/actions/runs/34232894885)，第三批广泛治理变更 | 16m49s | 13m42s / 13m29s | 13m17s |

两组后端慢分片的实际 `Run isolated shard` 步骤为 774–790 秒；macOS 的准备步骤
34–42 秒，backend gate 482–515 秒，Web gate 217–254 秒。由此可定位到测试执行
窗口，不能归因为单纯下载或队列等待。小改动也可能选择完整高风险门；这两个样本
不足以估计所有普通 PR 的分位数，更不能证明削减门禁或增加 runner 的收益。

后续仅在需要优化反馈时间时，先从慢分片的测试级记录和分配方式判断负载是否失衡，
同时保留平台验收边界。旧本地 #110 记录中的 OCI timeout 用例曾为 9.16 秒超过
8 秒，其单文件复测通过；这是调度敏感性的线索，不是放宽上限或增加重试的依据。
本次未修改分片、超时、coverage、runner 额度或验证收据政策。

进一步复核见 [Issue 127](https://github.com/cosmos-arc/ditto/issues/127)：本轮提交检查
又遇到 orphan-pipe 用例总耗时 8.05 秒。现有物理用例的 24 次八并发探测中有 6 次
失败；阶段测量另一次复现发现 inventory 为 5.37–6.63 秒，而运行仍约 3.005 秒，
清理不足 0.1 秒。原断言把另有 15 秒上限的 inventory 探测混入了运行阶段的 8 秒上限。
测试现在从 fake CLI 实际完成 inventory 的时间开始计量，仍包含运行启动与清理，
并增加 6 秒慢探测反例；生产实现和全部超时不变。该发现解释了已捕获样本，
不扩大为所有历史计时失败的根因，也不据此默认降低测试并发。

### 2026-09-27 验证阶梯与分片基线（[Issue 318](https://github.com/cosmos-arc/ditto/issues/318)）

测量条件：分支 `perf/318-verify-baseline` @ `b7d2e8ee`（origin/main，#316 后）、macOS
ARM64、uv 热缓存、无并行负载；长链条顺序执行避免争用，每命令单次实测。阶梯各级耗时
为组件之和（命令构成当时与 pre-push 分级一致；#340 后同一阶梯归 `task verify-push`
与 `check-changed`，pre-push 只核对身份/范围，见 agent-harness 文档）。

组件实测：

| 组件 | 命令 | 实测 |
| --- | --- | ---: |
| Ruff lint | `task lint` | 0.2s |
| Ruff format 检查 | `task fmt-check` | 0.1s |
| 类型（全仓） | `task type-all` | 40.6s |
| 类型（仅测试） | `task type -- --tests` | 22.6s |
| skills 验证 | `task harness-validate` | 1.2s |
| Web 全检 | `task check-web` | 135.6s |
| fast 测试 kernel | `task test -- --fast packages/kernel/tests` | 4.3s |
| fast 测试 application | `task test -- --fast packages/application/tests` | 191.3s |
| fast 测试 backend | `task test -- --fast apps/backend/tests` | 129.6s |
| PIT 专项（串行，本地链条；CI 由分片承载+证据核验 #350） | `task pit` | 59.6s |
| 系统测试 | `task test-system` | 377.4s |
| 全量门 | `task check` | 507.1s |
| 单个测试文件 | `pytest <file> -q` | 2.6s |
| collection 探针（仅源码档执行） | `--fast --collect-only` | kernel 3.2s / application 22.0s |

阶梯各档合计（组件相加，探针按 owner 计入单包源码档）：

| 档位 | 合计 |
| --- | ---: |
| 纯 docs | ≈0（无命令） |
| skills | 1.2s |
| 纯 web（不含 web-input 路径） | 135.6s；触及 specs/prototype 等输入路径时另加 `task web-prototype`（未实测） |
| 仅测试文件（单文件样本） | ≈25s（该档不执行 collection 探针；删除测试或改动非 py 夹具时按 owner 目录整跑，时长升至该包套件量级） |
| 单包后端 kernel / application（含探针） | 48s / 254s |
| 单包高危 application（含探针） | 314s |
| 跨包 / root / unknown（`task check`） | 507s |
| 跨栈/契约再叠加 `test-system` | 884s |
| 最高实测组合（check + test-system + pit，不含条件性 web-prototype 门） | 944s ≈ 15.7min |

观察：#322 只降档纯后端多 owner 档（契约/跨栈/根路径折叠条件保持全量）。配对对比——
纯后端跨包高危（application + backend）现行 ≈589s（探针 + `task check` + pit），#322 后
估算 ≈444s（约 -25%）；契约/跨栈叠加 `test-system` 的 944s 组合不在 #322 降档范围。

2026-09-28（#330 B1）同机复测 fast 车道：表达式去层级化后（`not slow and not serial
and not e2e and not snapshot and not sandbox_live and not capacity`，integration 目录项
因 blanket serial 退出、低成本显式集成/contract 项进入），kernel 285 例 3.3s、
application 4295 例 124.6s/134.5s（两复测；改动前同机 4469 例 110.5s——组成不同：
-174 个 integration 目录项、+61 个低成本集成项，墙钟在本机方差内持平，收益是选择
语义稳定而非时长）、backend 2108 例 62.3s。上表其余组件构成未变。
`task type-all` 40.6s 为全仓检查，单包档也整付（记录观察，本票不改）。

### 2026-10-06 类型门覆盖完整性（[Issue 539](https://github.com/cosmos-arc/ditto/issues/539)）

排查 #533 时发现 `pyright.tests.json` 的 `packages/*/tests` 单星 glob 在
basedpyright 中不展开（仅 `**` 生效）——12 个包 1020 个测试文件长期在类型门
外；`apps/backend/src` 248 个生产文件也仅是生产门的 extraPaths 而从未被报告。
同批修复：include 全部改字面目录清单（含根 `tests/`），生产门 include 显式纳
入 `apps/backend/src`，并真修暴露出的 backend 29 错与根 tests 5 错（其中
`r3_live_planning_builder` 三处为 #410 改名漏改的运行时断裂）。

语义与维护：

- tests 门存量债（2480 错，按包分布见 #539）钉在入库 `pyright.tests.baseline.json`
  （basedpyright 原生 baselineFile，由配置自动消费）；**新错误立即红**，存量不计。
- 每批清偿后重生成收缩：修错 → `rm pyright.tests.baseline.json` →
  `basedpyright --project pyright.tests.json --writebaseline` → 提交新基线；清零时
  连 `baselineFile` 配置一并移除。
- `tooling/quality/tests/test_type_gate_coverage.py` 守卫：tests include 必须与磁盘
  tests 目录集合完全一致、禁用通配符、生产门必须含 `apps/backend/src`——新包/新
  tooling tests 目录不登记即红，杜绝静默漏保。

CI 侧（9 次成功全量 PR + 3 次后端 squash push，2026-09-27 取样）：

- PR 全量 wall 778–831s（如 [run 36301251107](https://github.com/cosmos-arc/ditto/actions/runs/36301251107)）；
  关键路径 = backend-shards 最慢片 510–536s → Backend tests and coverage 242s；
  backend-capacity 已独立（196s）；macOS smoke ~584s 并行不在关键路径。
- 分片失衡：9/9 次运行均失衡，跨运行汇总最快片 320–367s、最慢片 510–536s；单次运行内
  最慢/最快比值为 1.42–1.64（如 367s vs 521s、320s vs 526s）。均衡分片后关键路径预计可省
  约 150–190s；是否做时长感知分片由后续票裁决。
- push 到 main 已收窄：ci.py 对 push 信任 PR 已验证的等价内容，仅补跑跨平台冒烟
  与常驻安全检查。#313/#310/#311 三次后端 squash push（runs
  [36276650225](https://github.com/cosmos-arc/ditto/actions/runs/36276650225)、
  [36275553446](https://github.com/cosmos-arc/ditto/actions/runs/36275553446)、
  [36263324989](https://github.com/cosmos-arc/ditto/actions/runs/36263324989)）均只执行
  Repository policy / Platform smoke / Security 组，backend-shards、backend-tests、web
  覆盖率/构建/原型/系统测试等专属 job 不再重跑；平台冒烟在 push 仍重跑 macOS
  `check-backend`/`check-web` 与 Windows `type-all`/`web-type`——后端与 Web 的基础门
  在 push 有实质重跑，去重的只是分片全量、覆盖率、契约与系统测试等重门。2026-09-18 诊断中"push 到 main 一律全量 16 分钟"的描述
  不再成立。

## 本次本机证据

2026-09-07 在同一 macOS ARM64 主机上比较迁移前后 Bun 效率。两侧均为独立临时 worktree、Bun 1.3.14、独立空安装缓存；冷安装执行一次 `bun ci --frozen-lockfile`，热安装立即用同一缓存重复执行。常用根检查在已准备环境上分别执行各自的 `web-type` 入口。

| 快照 | Bun 冷安装 | Bun 热安装 | 常用根检查 |
| --- | ---: | ---: | ---: |
| Pixi 基线 `2e8b8818` | 5.50 秒 | 0.02 秒 | `pixi run -e dev web-type` 20.96 秒 |
| uv/Task 迁移分支 | 9.91 秒 | 0.03 秒 | `task web-type` 21.47 秒 |

基线 Web 检查使用宿主 Node 24.18.0，迁移分支使用固定 Node 24.20.0。冷安装受网络波动影响明显，以上数字仅定位异常退化，不设任意性能门槛。Web 构建、208 文件/1757 项覆盖率测试、719 项原型测试、真实 API smoke 和 22 项优化器测试已通过。最终平台/整仓结果以本次实施记录及 CI 为准，不能由本页推断未运行的平台通过。

## 本地工具的独立路径

工具归档可解压到当前 checkout 的 `.cache/toolchains/`，入口放到其中的 `bin/`；
入口应解析到本 checkout 内的固定版本工具，不能指向已合并分支的其他 worktree。
从根目录设置 `export PATH="$PWD/.cache/toolchains/bin:$PATH"` 后运行 `task toolchain-check`。
这只影响当前 shell，不改写全局 Node/Bun/uv 设置。旧 Pixi 环境的处置依据见
[本地处置规则](knowledge-lifecycle.md#本地处置)；安装依赖不是删除真实状态的理由。
