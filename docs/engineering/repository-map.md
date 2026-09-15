# 仓库文件地图

根级每个文件与目录的作用、机器引用和处置边界。面向维护者；外部读者看 [README](../../README.md) 的简表。
基线为 2026-09 结构清理（Claude Code 宿主退役、Pixi 残留移除、codecov 配置迁移）后的状态，决策依据见
[wayfinder 地图 #142](https://github.com/cosmos-arc/ditto/issues/142) 及其子 ticket。

引用以机制（配置键、函数、task 名）描述，不绑定行号；行号随代码漂移，机制相对稳定。

## 根级单文件

| 文件 | 作用 | 机器引用 |
|---|---|---|
| `AGENTS.md` | 仓库级 agent 指南：事实入口、关键不变量、授权边界 | hook `_is_harness` 保护；每周 lychee 链接扫描 |
| `README.md` | 项目门面：定位、仓库地图、快速开始 | 每周 lychee 链接扫描 |
| `CHANGELOG.md` | 版本变更记录（发布历史） | GitHub 门面惯例，无机器引用 |
| `SECURITY.md` | 安全策略与 agent 会话边界 | GitHub 门面惯例，无机器引用 |
| `LICENSE` | 许可证 | 法律必需 |
| `Taskfile.yml` | 唯一跨栈任务 DAG；所有 `task` 入口 | CI workflows 全量调用；hook `_is_harness` |
| `pyproject.toml` | uv workspace 根 + Ruff/basedpyright/pytest 全家配置 | `task type/lint/test` |
| `uv.lock` | Python 环境锁（uv） | `task python-install --locked`；Dockerfile 构建输入 |
| `bun.lock` | Web 依赖唯一锁文件 | `task bun-install --frozen-lockfile`；repository_policy Bun-only 断言 |
| `bunfig.toml` | Bun 安装策略（isolated linker、禁 hoist、registry） | validate `_validate_structured_configs`；release 策略测试 |
| `package.json` | Bun workspace manifest，`packageManager` 钉死 Bun 版本 | `.github/actions/setup-bun` 解析 packageManager；release 版本比对 |
| `.github/codecov.yml` | Codecov 云端覆盖率门禁（阈值以该文件为准） | codecov-action 自动发现；`tooling/release/tests/test_codecov_policy.py` 策略断言 |
| `pyright.tests.json` | 测试代码独立 basedpyright 配置（basic 模式 + extraPaths） | `scripts/type.py` 以 `--project pyright.tests.json` 显式调用 |
| `.importlinter` | import-linter 架构契约：依赖边界的机器权威 | `task lint-imports`（import-linter 默认读根路径） |
| `.pre-commit-config.yaml` | pre-commit 钩子：ruff、gitleaks、conventional commits、pre-push | `task pre-commit-install/run/update` |
| `.gitleaks.toml` | gitleaks 配置（extend 默认规则集） | security workflow 单版本容器扫描；pre-commit gitleaks hook |
| `.gitleaksignore` | 已审计误报指纹（commit:path:rule:line 精确到行） | security workflow 扫描必须全过；策略测试禁止宽泛排除 |
| `.knowledge-policy.toml` | 机器输入位置哨兵 | `task harness-validate`(tooling/agent_harness/validate) |
| `.redocly.yaml` | OpenAPI lint 配置 | `task contract-static`；integrator lease 单写路径 |
| `.ignore` | ripgrep/fd 检索排除：历史材料对人开放、对 agent 检索隐藏 | 检索工具行为，无门禁 |
| `.gitattributes` | 生成物标记：eol=lf + linguist-generated（契约、schema 等） | 契约配置测试；hook `_ROOT_GATE_PATHS` |
| `.gitignore` | 忽略规则总表 | git 本身 |
| `.dockerignore` | docker build context 过滤 | release/ci 的 build-push-action（context: .） |
| `.node-version` / `.python-version` / `.task-version` | Node、Python、go-task 精确版本钉死 | setup-bun/setup-toolchain composite actions；toolchain.py；renovate fileMatch |

### `pyright.tests.json` 为何保留独立文件

源码检查用 `pyproject.toml` 的 `[tool.basedpyright]`（standard 模式），并通过 `ignore` 在 IDE 中抑制
tests 诊断；测试检查用本文件（basic 模式 + extraPaths）由 `scripts/type.py` 显式驱动。两套 profile +
IDE 抑制语义依赖「一个 pyright 项目只有一个配置文件」的机制，合并进 `pyproject.toml`
（含 executionEnvironments）无法在不改变 IDE 行为的前提下承载两者，故保留非默认命名。

## 根级目录

| 目录 | 作用 | 关键引用 |
|---|---|---|
| `.agents/` | 宿主无关 skill 唯一编辑源：`skills/ditto-pit-safety/` + `skills/registry.toml` | validator `SKILL_REGISTRY`；Codex/ZCode 直读；CI skill-validation |
| `.codex/` | Codex 宿主薄适配：hooks 接共享 `tooling/agent_harness/hook.py --host codex` | validator `_validate_host_configs` |
| `.zcode/` | ZCode 宿主薄适配：hooks 嵌套 `hooks.events` 且要求 `enabled: true` | validator `_validate_host_configs` |
| `packages/` | 13 个能力包（kernel 零依赖核心 → application 编排 → agent 消费者），各含 AGENTS.md | `.importlinter` 契约；pytest testpaths |
| `apps/` | `backend`（唯一 Python composition root，FastAPI/CLI/Jobs）与 `web`（React SPA） | Taskfile、release workflow |
| `contracts/` | 跨栈契约：`openapi/v1.json` 快照、`cohorts/` 兼容策略 | `task check-contract`；Web 构建内嵌 policy |
| `tooling/` | 内部工具包：agent_harness / contracts / dev / quality / release | Taskfile 全量；CI 各 job |
| `scripts/` | 任务图辅助脚本（type/test/architecture/analyze-slow-tests）+ 验收与证据工具 | 见下节 |
| `config/` | 运行时配置：`default/` DQ 规则与环境 `.env` 域文件 | platform config loader `config/{environment}/*.env` |
| `deploy/` | docker / observability / agent-sandbox 三分支部署材料 | release workflow；sandbox 验收脚本 |
| `tests/` | 根级 Playwright 系统 E2E + fixture app | `task test-system`（tooling/dev/system_tests） |
| `typings/` | 第三方 pyright stub（annotationlib、dishka、opentelemetry） | pyproject `stubPath` |
| `artifacts/` | tracked 历史验收证据（r2/r3/rc1 报告），不可当死数据删除 | r3 验收脚本 `--r2-evidence`；gitleaks 指纹；pre-commit 排除 |
| `docs/` | 文档域：architecture / adr / engineering / agents + archive 历史区 | `.ignore` 隐藏 archive；每周 lychee |
| `.github/` | workflows、composite actions、CODEOWNERS、PR 模板、renovate、codecov.yml | `uses: ./.github/actions/...` |

## scripts/ 内的游离工具

- `scripts/analyze_slow_tests.py`、`type.py`、`test.py`、`architecture/`：Taskfile 活跃引用，保留。
- `scripts/acceptance/`：rc1/wave1/r2 验收可重放工具链；r3 验收链仍读 `artifacts/acceptance/` 前置报告。保留。
- `scripts/evidence/`：个人工作站证据文档的「可重放命令」载体。保留。
- `scripts/benchmarks/`：保留的手动基准入口，无 Taskfile/CI 自动执行；仅在对应研究问题需要测量时使用。

## 本地运行时目录（gitignored，不进仓库）

| 目录/文件 | 再生方式 | 处置 |
|---|---|---|
| `htmlcov/`、`coverage.*`、`.coverage` | `task test -- --cov` | 可随时删；`task clean` 覆盖 |
| `.pytest_cache/`、`.ruff_cache/`、`.import_linter_cache/`、`.hypothesis/` | 对应工具任意运行 | 可随时删 |
| `build/`、`dist/` | test-shards / release 排练 | 可随时删；`task clean` 覆盖 build/ |
| `.cache/` | dev supervisor / system tests / 工具链缓存 | 无运行中服务时可删 |
| `logs/` | 后端日志默认目录 | 可删（空态） |
| `.tmp/` | 验收脚本与 lease 的临时区 | **删除前甄别**：历史上混有个人 scratch（planning-*.json、closure 草稿） |
| `.pixi/` | 无（工具链已统一 uv） | 已退役；忽略规则保留——旧 worktree 更新后残留目录不进入 untracked 变更集 |
| `data/` | 行情可重下；**state 不可再生** | **不可随手删**：含 `evidence-signing.key` 与个人验收 sqlite |
| `node_modules/`、`.venv/` | `task bun-install` / `task python-install` | 可再生，重装耗时 |

## 已退役记录

- **Claude Code 宿主（2026-09）**：`.claude/`（settings + skills 镜像）、根与全部包级 `CLAUDE.md` wrapper、
  `sync-agent-skills` 生成链与 validator 镜像校验一并移除；宿主集合收敛为 Codex + ZCode，
  `.agents/skills` 成为唯一技能源。validator `LEGACY_PATHS` 收录被删路径防倒退。历史归档文档中的
  Claude 记载不改写。
- **Pixi（2026-09，#97 决议统一 uv）**：pyproject 的 pixi 排除与注释、runtime-path 测试的
  `pixi.toml` checkout 标记已清理；`.gitignore`/`.dockerignore` 保留 `.pixi`
  忽略条目（旧 worktree 残留目录防噪）；历史文档中 `pixi run` 记载属历史事实，不改写。
