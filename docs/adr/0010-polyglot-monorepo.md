# 0010 - 联邦式双技术栈 Monorepo

**状态**：Accepted

**日期**：2026-09-04

**取代**：[ADR 0002](0002-monorepo-structure.md)

## 背景

Ditto 后端是由 13 个 Python package 组成的模块化单体，使用 Pixi、FastAPI、
Polars 和 import-linter。用户界面原位于独立的 `ditto-app` 仓库，使用 Bun、
React、TypeScript、Vite 和 TanStack。两个仓库分别维护 CI、Agent 指令、Skills、
Harness 和 OpenAPI 生成流程，导致同一产品行为不能由同一提交完整证明，且两个
Harness 都无法识别未跟踪文件。

本决策关注正确性、可审计性和多 Agent 的局部可推理性。目录合并本身不是目标；
目标是让 API provider、跨语言契约、Web consumer、跨栈验收和发布证据形成一个
机器可验证的变更单元。

## 决策

### 1. 仓库与制品模型

采用联邦式 polyglot monorepo：

```text
ditto/
├── apps/
│   ├── backend/        # FastAPI/CLI/Jobs/composition root，导入名仍为 ditto_apps
│   └── web/            # React SPA
├── packages/           # 其余 12 个 Python capability packages
├── contracts/openapi/  # 唯一跨语言 API 契约
├── tests/system/       # production Web + 隔离 API 的跨栈验收
├── tooling/            # 跨栈契约、Harness、质量和开发工具
├── pixi.toml
└── package.json
```

后端和 Web 继续生成独立制品，但正式发布属于同一个 release cohort。每个 cohort
记录产品版本、Git SHA、OpenAPI SHA-256 和两个制品 digest。

### 2. 能力平面、provider、consumer 与合同

| 能力 | Provider | 直接 consumer | 合同 |
|---|---|---|---|
| 后端业务能力 | 12 个 Python capability package | `application` | Python 源包公共 API 与 import-linter contracts |
| 用例编排 | `application` | `agent`、`apps/backend` | commands/queries/processes |
| HTTP API | `apps/backend` | 契约生成器与 Web | FastAPI route + stable `operationId` |
| 跨语言语义 | `contracts/openapi/v1.json` | `apps/web/src/api` | OpenAPI 3.1 snapshot + SHA-256 |
| Web transport | `apps/web/src/api` | feature API adapters | `openapi-fetch` 与生成的 `paths` 类型 |
| 跨产品工作流 | `apps/web/src/workflows` | routes/app composition | feature public APIs，不允许 feature 环 |

Web 不导入 Python DTO、后端源码或存储模型。后端不读取 Web 状态或 Web 生成物。
`agent` 仍只能经 `application` 使用业务能力；同仓不改变 13 包的依赖方向、PIT
fail-closed 语义或唯一 composition root。

### 3. 工具所有权

- 根 `pixi.toml` 是唯一跨栈任务 DAG 和用户入口。
- Pixi 管理 Python 环境；Bun workspace 管理 Web 依赖和叶子任务。
- 根 Bun workspace 使用唯一文本 `bun.lock`；禁止引入 pnpm/npm/yarn lockfile。
- 当前不引入 Nx、Bazel、Pants 或 Turborepo。
- 验证任务不使用 task-result cache；只有输入声明完整且有 soundness 测试的确定性
  build/codegen 才可缓存。

### 4. 契约方向

```text
apps/backend FastAPI
  -> contracts/openapi/v1.json
  -> apps/web/src/api/generated/schema.d.ts
  -> typed transport
  -> feature adapter
  -> view model / UI
```

OpenAPI snapshot 是唯一跨语言事实源。生成类型提交 Git，但只允许生成器修改。
错误 path、method、query、body 和 response 必须在 TypeScript 或契约测试中被拒绝。

### 5. 路径语义

明确区分：

- `workspace_root`：只供开发工具与测试使用；
- `config_root`：运行时显式配置；
- `state_root`：SQLite、账本和运行状态；
- `cache_root`：可安全删除的缓存；
- `contract_root`：只供契约生成和验证工具使用。

生产运行时不得通过 `.git`、`pixi.toml` 或固定 `parents[n]` 推断状态和配置路径。

### 6. 机器执行

以下门禁共同执行本决策：

- `.importlinter` 与 Python architecture smell checks；
- Web alias-aware dependency graph、cycle、deep import 和 public API checks；
- OpenAPI export/lint/breaking/codegen zero-diff；
- production Web + isolated API system E2E；
- 根 Harness 对 staged、unstaged、untracked、rename/delete 和 mode 变化的分类与 receipt；
- GitHub Actions 的稳定 `ci-gate` 汇总门。

## Git 历史决策

现有后端仓库继续作为 canonical root，不重写后端历史。前端所有相关 refs 在隔离
clone 中使用固定版本的 `git-filter-repo --to-subdirectory-filter apps/web` 重写，
保存旧到新 commit map、bundle、refs、tree、作者和 timestamp 验证证据。历史导入、
`packages/apps -> apps/backend` 机械移动、配置合并和行为整改必须保持为可区分的阶段。

旧 `ditto-app` 仓库只有在 monorepo 门禁和恢复证据全部成立后才允许归档。

## 后果

积极面：

- 一个 Git 提交可原子证明 provider、contract、consumer 与真实跨栈行为。
- Python 与 TypeScript 继续使用各自成熟工具，不引入第二任务图。
- 根 Harness 和 CI 可以对跨栈影响 fail closed。
- 完整保留前端历史和旧到新 SHA 可追溯性。

代价：

- 根工具、CI 和 Agent 治理必须理解两种生态。
- 完整验证成本高于 affected-only 流程。
- 独立制品需要额外的 cohort manifest 和兼容性检查。
- 历史导入会增加仓库体积，短期运行证据必须迁出 tracked tree。

## 考虑的替代方案

### 保持两个仓库

拒绝。跨仓绝对路径、人工契约比较和分离 CI 无法提供同提交的正确性证据。

### Git submodule 或 subtree 同步

拒绝。它们保留两个提交坐标或需要同步约定，仍不能把产品行为变成单一原子变更。

### Nx 作为根控制面

暂不采用。当前只有一个 Web 应用和一个 Python 模块化单体，Nx 会引入第二任务图、
第二缓存模型，并无法原生理解 13 个 Python package 的真实边界。只有达到已记录的
应用/package 数量、CI 时延或可信跨机器缓存需求阈值后，才通过新 ADR 复评。

### Bazel、Pants 或 Turborepo

拒绝。Bazel 的 hermetic 收益不足以抵消第三套依赖语义；Pants 的 TypeScript/Bun
支持不满足目标；Turborepo 无法理解 Python 架构边界。

## 验收

本 ADR 只有在以下条件同时成立时才视为落地：

1. 后端原历史 SHA 保持不变，前端所有导入 ref 可由 commit map 追溯。
2. 根 Pixi/Bun workspace 可从干净 runner bootstrap。
3. Python 和 Web dependency graph 均为严格绿灯。
4. OpenAPI snapshot、generated types 与 typed transport 构成 zero-diff 门禁。
5. production Web 与隔离 API 的核心 system E2E 通过。
6. 根 Harness 对纯未跟踪文件的回归测试通过。
7. 两个 release artifact 与 cohort manifest 的 SHA/digest 一致。
