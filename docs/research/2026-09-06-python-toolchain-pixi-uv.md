# Python 包管理与原生环境：Pixi 和 uv 的长期适配

调研日期：2026-09-06。仓库基线：`2e8b8818634275a4eba60b460d01434966ab5b15`。对应决策票：[Python 包管理与原生环境：Pixi 和 uv 的长期适配](https://github.com/cosmos-arc/ditto/issues/98)。只评估长期系统适配，不计算迁移投入；本次未安装依赖、生成新锁、迁移配置或执行应用测试。

## 判断

**对 Ditto 当前已知产品形态，建议以 uv workspace 作为长期 Python 包与项目环境管理方向。** 依据是：仓库的交付和边界单位是 13 个标准 Python 包；当前没有必须由 conda 统一解决的显式跨语言库、编译器或 GPU 环境要求；最主要原生 Python 依赖在已支持平台均有可用 wheel。将 Python 依赖收敛到一个 PyPI 求解体系，符合这里的实际边界。这个结论是根据仓库和官方能力做出的工程判断，不是“uv 是业界唯一标准”的事实断言。

**这不等于用 `uv run` 替换整个 Pixi。** Pixi 还承担真实的跨栈任务 DAG，uv 不提供对应的任务依赖图。若决定移除 Pixi，必须先确定 DAG 的唯一归属；否则只完成了部分替换，系统方向并不完整。也不建议因为“以后可能需要原生库”默认同时保留两套 Python 依赖权威。未来确有 conda 环境需求时，应明确环境边界。

## 仓库实际使用了什么

- 根 [pixi.toml](../../pixi.toml) 声明 `win-64`、`linux-64`、`osx-arm64`，Python `3.13.*`；`default` 与含开发工具的 `dev` 共用 `solve-group = "default"`。没有名为 `production` 的独立环境，Docker 使用 `default`。
- 13 个 editable 本地包：12 个 `packages/*` 加 `apps/backend`。它们已经采用 `[project]` 元数据及 `setuptools.build_meta`；根 [pyproject.toml](../../pyproject.toml) 约束 `>=3.13,<3.14`，叶包要求 `>=3.13`。运行依赖分布在叶包元数据和根 Pixi 约束中；采用 uv 后仍须保持“包声明自身依赖，工作区维护统一解”的责任，不能只机械搬运根列表。
- 根显式 conda 运行依赖为 Python、NumPy、Polars、DuckDB、FastAPI、Pydantic、pydantic-settings、HTTPX、python-dotenv、Loguru、PyYAML、Typer、Prefect、Lupa。开发部分也是 Python 生态可获得的工具。没有显式 CUDA、GDAL、ffmpeg、C/C++ 编译器等环境要求。
- **项目确有大量原生依赖。** [pixi.lock](../../pixi.lock) 包含 BLAS/LAPACK、OpenBLAS 或 MKL、Lua、C/C++ 运行库；PyPI 部分已经锁定 CVXPY 1.9.2、SciPy 1.18.0、OSQP 1.1.3、Clarabel 0.11.1、SCS 3.2.11 的三平台 wheel。“没有 native 依赖”是错误描述。真正的问题是这些依赖是否需要在 wheel 之外统一管理系统 ABI。
- 根有 **61 个普通 task，其中 12 个声明 `depends-on`**，另有 1 个 dev 专属 task。`check`、`ci`、`bootstrap`、`web-ci`、`artifact-gate` 串接后端、Web、契约、安全与制品验收。这是现存系统能力，不是可删的迁移成本。
- [Dockerfile](../../deploy/docker/Dockerfile) 在 Pixi builder 中安装 `default`，再向固定 digest 的 Debian runtime 复制环境和源码；本地包仍按 editable 声明安装。目前不是先构建 13 个 wheel 再安装的制品路径。两种工具都可以改进为独立制品安装，不能把当前 Docker 写法当作 Pixi 的能力上限。

## 同一锁文件的实际平台差异

按 lock 中每个 environment 的平台引用逐项确认，下面不是没有被使用的旧 record；`default` 和 `dev` 在同一平台上的这些版本一致。

| 目标平台 | Python | NumPy | Polars / runtime | DuckDB | Lupa | BLAS 变体 |
|---|---|---|---|---|---|---|
| Linux x86_64 | 3.13.13 | 2.4.3 | 1.40.0 | 1.5.2 | 2.8 | OpenBLAS |
| Windows amd64 | 3.13.13 | 2.4.3 | 1.40.0 | 1.5.2 | 2.8 | MKL |
| macOS arm64 | 3.13.14 | 2.5.1 | 1.43.2 | 1.5.5 | 2.8 | OpenBLAS |

**“一个 lock”不代表“跨 OS 每个包同版本”，也不代表浮点计算逐位一致。** Pixi 按平台求解，同一 solve-group 约束环境之间的共享版本；uv 的 universal resolution 同样允许按 Python/平台 marker 分叉。跨平台一致性是需要显式约束和数值验收的产品要求，不是更换文件名就能获得的性质。[Pixi 多环境](https://pixi.prefix.dev/latest/workspace/multi_environment/)、[Pixi 与 uv 的锁模型比较](https://pixi.prefix.dev/latest/switching_from/uv/#lockfiles)、[uv resolution](https://docs.astral.sh/uv/concepts/resolution/)。

## 对当前版本的 PyPI wheel 核验

通过公开 PyPI release JSON 只读查询 `urls`、`requires_python`、`yanked` 和 wheel filename。这里的“三平台支持”限定为标准 CPython 3.13、Windows amd64、glibc Linux x86_64、macOS arm64；不是 Python free-threaded、Alpine/musl 或任意旧 OS/CPU 的保证。表中匹配产物都未被 yank。

| 库及当前 lock 中的版本 | Windows amd64 | Linux x86_64 | macOS arm64 | 一手记录 |
|---|---|---|---|---|
| NumPy 2.4.3、2.5.1 | `cp313-cp313-win_amd64` | `cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64` | `cp313-cp313-macosx_11_0_arm64`，也有 macOS 14 变体 | [2.4.3 JSON](https://pypi.org/pypi/numpy/2.4.3/json)、[2.5.1 JSON](https://pypi.org/pypi/numpy/2.5.1/json) |
| Polars 1.40.0、1.43.2 | wrapper 是 `py3-none-any` | 同左 | 同左 | [1.40.0 JSON](https://pypi.org/pypi/polars/1.40.0/json)、[1.43.2 JSON](https://pypi.org/pypi/polars/1.43.2/json) |
| polars-runtime-32 1.40.0、1.43.2 | `cp310-abi3-win_amd64` | `cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64` | `cp310-abi3-macosx_11_0_arm64` | [1.40.0 JSON](https://pypi.org/pypi/polars-runtime-32/1.40.0/json)、[1.43.2 JSON](https://pypi.org/pypi/polars-runtime-32/1.43.2/json) |
| DuckDB 1.5.2、1.5.5 | `cp313-cp313-win_amd64` | `cp313-cp313-manylinux_2_26_x86_64.manylinux_2_28_x86_64` | `cp313-cp313-macosx_11_0_arm64`，也有 universal2 | [1.5.2 JSON](https://pypi.org/pypi/duckdb/1.5.2/json)、[1.5.5 JSON](https://pypi.org/pypi/duckdb/1.5.5/json) |
| Lupa 2.8 | `cp313-cp313-win_amd64` | `cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64` | `cp313-cp313-macosx_11_0_arm64` | [2.8 JSON](https://pypi.org/pypi/lupa/2.8/json) |

Polars wrapper 的元数据明确要求相同版本 `polars-runtime-32`，所以不能看到 `py3-none-any` 就称 Polars 为纯 Python。`cp310-abi3` 使用稳定 ABI，可覆盖 CPython 3.13；manylinux 和 macOS tag 仍带有最低平台约束。[PyPA 平台兼容标签](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)。

这个检查证明“主要已锁原生依赖具备 PyPI 二进制分发条件”，没有证明整个项目已经在 uv 下成功求解，更没有证明 wheel 与 conda 构建的数值行为、BLAS、Lua 变体完全等价。

## 两种工具的系统边界

| 维度 | Pixi 的实际能力 | uv 的实际能力及 Ditto 判断 |
|---|---|---|
| Python / 原生环境 | 同时管理 conda 与 PyPI；conda 包可声明独立原生库及运行时 ABI 约束 | 管理 Python 分发及其 wheel/sdist，不充当通用 OS 原生依赖求解器。当前主要需求由 wheel 满足，uv 边界更贴合 |
| 求解过程 | 使用 uv 库处理 PyPI；先求解 conda，再映射到 PyPI 名称、求解剩余 PyPI 依赖 | 单一 Python 包求解体系；收益在去除当前不必要的两套生态协调，而非“Pixi 没有 uv 的快速 resolver” |
| 多包工作区 | 当前可以将 13 个本地包纳入一个环境；也支持标准 pyproject 输入 | 原生 workspace，成员各自声明 pyproject，共用 uv.lock；支持按 package 同步/运行。与当前共同发布的 Python 包集合自然对应 |
| 开发 / 生产 | 可锁定多个具名环境，允许独立解或 solve-group 共享解；各有环境目录 | 标准 dependency groups，默认包含 dev，可排除 dev；普通 workspace 共享一个项目环境。生产应在独立构建环境安装，不能假定切换 group 自动保留多个持久环境 |
| 多平台锁 | 在一个文件保存明确目标平台、多个环境的 conda 与 PyPI 产物 | universal lock 跨 Python/OS/架构 marker；同样可能分叉版本。锁成功也不等于已实测所有目标 |
| Python 本身 | Python 是 conda 依赖，lock 含精确解释器包及其构建产物 | 能下载、发现、选择和 pin Python；managed CPython 来自 python-build-standalone。uv.lock 不是解释器及系统库的完整产物锁，解释器来源/版本应另行固定 |
| 任务执行 | 支持依赖图、统一跨平台 shell、任务环境和输入输出缓存 | `uv run` 负责环境中的命令执行；不能据此宣称具备 Pixi 的 task DAG |

来源：[Pixi Conda/PyPI 与双 solver](https://pixi.prefix.dev/latest/concepts/conda_pypi/)、[conda runtime requirements / run_exports](https://docs.conda.io/projects/conda-build/en/stable/resources/define-metadata.html#export-runtime-requirements)、[uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)、[uv dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups)、[uv Python 管理](https://docs.astral.sh/uv/concepts/python-versions/)、[Pixi tasks](https://pixi.prefix.dev/latest/workspace/advanced_tasks/)。

uv workspace 也不是包之间的导入隔离器，仍不能阻止一个包导入另一个成员所安装的第三方库。Ditto 的叶包依赖声明、import-linter 与干净制品验收继续有价值；不是用了 workspace 就可删除。[uv workspaces 的限制](https://docs.astral.sh/uv/concepts/projects/workspaces/#when-not-to-use-workspaces)。

## 标准、可复现和制品需要分开评价

1. **标准元数据不是 uv 独有。** `[project]`、`[build-system]`、dependency groups 是 Python 生态标准；Pixi 也能读取 `pyproject.toml` 的项目依赖、optional dependencies 与 dependency groups。uv 的 workspace/source 配置则是工具扩展。采用 uv 的理由是系统适配，不是说 Pixi 不能使用标准。[PyPA pyproject 规范](https://packaging.python.org/en/latest/specifications/pyproject-toml/)、[Pixi pyproject 支持](https://pixi.prefix.dev/latest/python/pyproject_toml/)。
2. **uv.lock 仍是 uv 专用格式。** 标准的跨工具锁输出是 PEP 751 `pylock.toml`；uv 可 export 到它并在 pip 接口中消费，但 project 工作流继续用 uv.lock，因为它表达了额外功能。不能写“改用 uv 就摆脱了专用 lock”。[uv lock 与 pylock 的关系](https://docs.astral.sh/uv/concepts/projects/layout/#relationship-to-pylocktoml)。
3. **可复现需要核验，不只是提交一个锁。** uv 的 `--locked` 要求锁与元数据一致，`--frozen` 跳过锁新鲜度检查；Pixi 也有同样需要区分的选项。生产和 CI 应有锁新鲜度校验、固定工具/解释器来源及精确产物身份。[uv locking/sync](https://docs.astral.sh/uv/concepts/projects/sync/)、[Pixi lock](https://pixi.prefix.dev/latest/workspace/lock_file/)。
4. **非 editable 生产安装是目标行为，不是选型口号。** uv 的 Docker 官方方案提供 workspace 分层缓存、`--no-dev` 与 `--no-editable`；运行镜像可只带解释器、已安装包和应用资源。使用 uv 不要求更换现有 setuptools，也不必在运行容器内保留 uv。Pixi 也能承担制品构建/环境交付；应比较最终产物的隔离、可验证性与支持边界。[uv Docker](https://docs.astral.sh/uv/guides/integration/docker/)、[Pixi 容器交付](https://pixi.prefix.dev/latest/deployment/container/)。

## 保留 Pixi 的最强理由与改判条件

最强反方论点是：Ditto 是三平台本地量化工作站，已经消耗 NumPy/BLAS、Lua 等原生组件；Pixi 能把解释器、原生运行库、开发环境和任务 DAG 一起放进同一环境模型。这个收益即使完全忽略迁移成本也成立，尤其是将来要控制 BLAS/MKL 变体、链接项目自建 C++ 扩展，或交付离线的完整原生运行环境时。wheel 存在只意味着能安装，不能代替这种环境控制。[Pixi conda 生态](https://pixi.prefix.dev/latest/conda_ecosystem/)、[conda ABI 运行依赖](https://docs.conda.io/projects/conda-build/en/stable/resources/define-metadata.html#export-runtime-requirements)。

满足以下任一实际需求时，应重新倾向 Pixi；它们是改判条件，不是预设的未来路线：

- 目标平台所需的关键包没有可靠 wheel，或必须统一管理 wheel 之外的共享库、编译器、GDAL、CUDA 等。
- 产品明确要求控制 NumPy 与其他本地扩展共享的 BLAS/系统库构建变体，且普通 Python 二进制分发不能满足。
- 需要多个相互冲突的解释器或原生软件环境共同锁定、分发，并由同一任务模型选择。
- 对完整解释器及原生环境产物的跨平台锁定，价值高于 Python-only 包生态的单一求解和常规 wheel 交付。

现在尚未看到这些必要条件。现有显式 conda 条目都能归入 Python 包管理，且主要重型依赖已有 wheel，因此**uv 是较合适的 Python 默认方向；Pixi 是有真实额外环境需求时仍正确的选择**。单凭“量化 / 科学计算”分类，不足以替项目作出 conda 必需的判断。

## 仍需验证的边界

本报告足以支持选型方向，不能当成迁移验收：未生成 uv workspace/uv.lock，未核验全量传递依赖在三平台的 binary-only 求解；未实跑 API、优化求解器或原生 import；未比较 NumPy/BLAS 数值与线程行为、Lupa Lua 变体、Polars CPU 要求；未测性能、镜像大小或完整离线安装。DAG 的具体替代工具也不由这张 Python 研究票决定。
