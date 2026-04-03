# 目录结构清理与优化设计

> 日期：2026-04-04
> 状态：已批准
> 范围：删除废弃目录、扁平化 app 层级、统一配置、清理 git 追踪

---

## 背景

项目决定不再与前端共享 repo（非 monorepo），本仓库仅作为量化系统后端，暴露 CLI / API / Job / Messaging 界面端口。`apps/web` 已无存在意义，目录结构随迭代累积了大量冗余。

## 业界对标

经调研 PyPA、pyOpenSci、uv workspaces 文档，以及 Qlib / LEAN / Zipline / VectorBT 等量化系统项目：

- **`src/` layout** ✅ — 已符合 2025 标准
- **多包 monorepo** ✅ — `packages/` + 单 app 模式符合 uv workspace 标准
- **测试 co-located** ✅ — monorepo 常见做法（Dagster 推荐）
- **根级 `config/`** ✅ — Qlib/LEAN 均使用类似模式
- **领域驱动包划分** ✅ — data/engine/analytics/app 符合行业共识

**结论：当前结构方向正确，本次仅做减法和清理，不做结构性调整。**

---

## 变更清单

### 1. 删除废弃目录/文件

| 目标 | 原因 |
|------|------|
| `apps/web/` | 前端独立仓库，当前全为空占位符 |
| `apps/` 目录层 | 扁平化，只留 `interfaces/` |
| `scripts/learning/` | 个人学习工具（Anki/Obsidian），不属于项目 |
| `pixi.lock.backup` | git 历史可回溯，无需保留 |
| `packages/engine/data/` | SQLite 数据库不应入库 |
| `packages/data/.benchmarks/` | 缓存目录不应入库 |
| `packages/infra/.benchmarks/` | 缓存目录不应入库 |
| `coverage.xml` | 已在 .gitignore 但仍被 git 追踪 |

### 2. 扁平化 app 层级

```
apps/interfaces/  →  interfaces/
```

同步更新：
- `pixi.toml` 中 `pypi-dependencies` 的 path 引用
- `.importlinter` 中相关路径（如有）
- `.claude/` 和 `.factory/` 中相关路径（如有）
- `pyright.tests.json` 中相关路径（如有）

### 3. 迁移根级测试到 interfaces

```
tests/e2e/          → interfaces/tests/e2e/
tests/fixtures/     → interfaces/tests/fixtures/
tests/reports/      → interfaces/tests/reports/
tests/scripts/      → interfaces/tests/scripts/
tests/tdx_samples/  → interfaces/tests/tdx_samples/
tests/__init__.py   → 删除（迁移后根 tests/ 目录清空）
```

### 4. 统一配置到根级 config/

```
packages/data/config/  →  config/default/   （dq_rules 合并）
```

同步更新代码中引用 `packages/data/config/` 的路径。

### 5. .gitignore 更新

新增：
```gitignore
packages/*/data/               # 包内数据目录
*.sqlite                       # SQLite 数据库
*.sqlite-journal
pixi.lock.backup
```

`git rm --cached` 清理：
- `coverage.xml`
- `packages/engine/data/` 下的 sqlite 文件
- `packages/data/.benchmarks/`
- `packages/infra/.benchmarks/`

---

## 目标结构

```
ditto/
├── config/                    # 统一配置（所有环境 + 领域规则）
│   ├── default/               # 默认配置（含 dq_rules）
│   ├── development/
│   ├── testing/
│   └── production/
│
├── deploy/                    # 部署配置（不变）
│   ├── docker/
│   └── observability/
│
├── docs/                      # 文档（不变）
│
├── interfaces/                # 唯一应用入口（原 apps/interfaces/）
│   ├── src/ditto_interfaces/  # API / CLI / Jobs / Registry
│   └── tests/                 # 所有测试
│       ├── unit/
│       ├── integration/
│       ├── e2e/               # ← 从根 tests/ 迁入
│       ├── fixtures/          # ← 从根 tests/ 迁入
│       ├── reports/
│       ├── scripts/
│       └── tdx_samples/
│
├── packages/                  # 核心包（不变）
│   ├── infra/
│   ├── kernel/
│   ├── data/
│   ├── analytics/
│   ├── app/
│   └── engine/
│
├── scripts/                   # 开发脚本
│   ├── benchmarks/
│   ├── analyze_slow_tests.py
│   ├── check_code_size.py
│   ├── test.py
│   ├── type.py
│   └── verify-all-2025.sh
│
├── typings/                   # 类型补丁（不变）
│
├── CLAUDE.md / AGENTS.md / README.md
├── pixi.toml / pixi.lock
├── pyproject.toml
├── pyright.tests.json
├── .importlinter / .pre-commit-config.yaml / .dockerignore
└── codecov.yml
```

---

## 不在本次范围

- uv workspaces 迁移（后续独立考虑）
- 包内领域模型重组
- CI/CD 配置变更
