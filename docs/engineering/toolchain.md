# 开发与发布工具链

Task 是根任务图；uv 管理 13 个 Python distribution；Bun 保留 Web 安装与专用 API，Node 执行 Node CLI。版本声明分别在 `.task-version`、`pyproject.toml` 的 `tool.uv.required-version`、`.python-version`、`package.json` 的 `packageManager` 和 `.node-version`。

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

Task 的组合任务顺序调用前置任务，失败立即传播；构建完成后才能消费其输出。验证没有结果缓存。`.venv`、`.cache`、构建输出和 Git receipts 属于各自 worktree；uv/Bun 下载缓存和校验后的 oasdiff 归档可共享。

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

生产容器仅复制非 editable 环境、固定 Python 运行时、必要系统库与配置，不复制源码 checkout、uv 或 Bun。两个复制库来源镜像在 release cohort 中均有按 amd64 digest/config 绑定的原始 Trivy 报告；报告保留全部 package inventory，来源镜像中带 HIGH/CRITICAL 的 installed file 必须在最终镜像中不存在，或与来源字节不同（即已被干净来源替换），否则失败。独立的 copied-library source provenance SPDX 通过 external document reference 挂到最终 backend SPDX，原始来源报告也直接发布为 release evidence。环境身份是版本化摘要，绑定 `uv.lock`、`.python-version`、Dockerfile 的固定来源及目标 `linux/amd64`；release inputs 携带全部输入，新 bundle 携带对应 stdlib verifier。历史 cohort 与其自带 verifier 不改写。

## CI 时长基线

通过 run [34100716341](https://github.com/cosmos-arc/ditto/actions/runs/34100716341) 中，`Backend tests and coverage` 约 31 分 44 秒，整轮 CI 约 33 分 18 秒；16,501 个测试通过、74 个跳过。最慢的真实测试组为 scheduler capacity `[2]` 345.70 秒、capacity `[4]` 300.20 秒和 128-candidate backend e2e wrapper 303.20 秒。它们在 job 内并发，但合计占据主要窗口；这不是 public repo quota、`TUSHARE_TOKEN` 或 release scanner 造成的。release 扫描共享 Trivy DB volume，避免最终镜像与来源镜像扫描重复下载漏洞库。


## 本次本机证据

2026-09-07 在同一 macOS ARM64 主机上比较迁移前后 Bun 效率。两侧均为独立临时 worktree、Bun 1.3.14、独立空安装缓存；冷安装执行一次 `bun ci --frozen-lockfile`，热安装立即用同一缓存重复执行。常用根检查在已准备环境上分别执行各自的 `web-type` 入口。

| 快照 | Bun 冷安装 | Bun 热安装 | 常用根检查 |
| --- | ---: | ---: | ---: |
| Pixi 基线 `2e8b8818` | 5.50 秒 | 0.02 秒 | `pixi run -e dev web-type` 20.96 秒 |
| uv/Task 迁移分支 | 9.91 秒 | 0.03 秒 | `task web-type` 21.47 秒 |

基线 Web 检查使用宿主 Node 24.18.0，迁移分支使用固定 Node 24.20.0。冷安装受网络波动影响明显，以上数字仅定位异常退化，不设任意性能门槛。Web 构建、208 文件/1757 项覆盖率测试、719 项原型测试、真实 API smoke 和 22 项优化器测试已通过。最终平台/整仓结果以本次实施记录及 CI 为准，不能由本页推断未运行的平台通过。
