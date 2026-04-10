# Basedpyright 配置修复设计

> 日期：2026-04-08
> 状态：待实施

## 问题概述

basedpyright 在 VS Code 编辑器和终端 `pixi run -e dev check` 两个场景下均频繁出现类型解析失败。

## 根因分析

| # | 严重度 | 问题 | 影响 |
|---|--------|------|------|
| 1 | 高 | `annotationlib` 标准库模块在 conda-forge Python 3.13.12 中缺失 | typeshed 解析 `typing`/`typing_extensions`/`_typeshed` 失败，连锁误报 |
| 2 | 中 | 未配置 `venvPath`/`venv`，依赖自动发现 | VS Code 扩展找不到 pixi 虚拟环境，所有第三方包解析失败 |
| 3 | 中 | `pyright.tests.json` 缺少 4 个 extraPaths | 测试文件跨包 import（kernel/engine/app/interfaces）解析失败 |
| 4 | 中 | `pyright.tests.json` Python 版本为 `3.12`，实际为 `3.13.12` | 测试文件类型检查基于错误的 Python 版本 |
| 5 | 低 | `scripts/type.py` 每次无条件清除缓存 | 全量冷启动拖慢反馈速度 |

## 修复方案

### Fix 1：显式配置虚拟环境路径

**文件**：`pyproject.toml` `[tool.basedpyright]`

```toml
venvPath = ".pixi/envs"
venv = "dev"
```

确保 VS Code 扩展和 pixi shell 都能准确定位虚拟环境。

### Fix 2：添加 `annotationlib` stub

**文件**：`typings/annotationlib.pyi`（新建）

conda-forge Python 3.13.12 未打包 `annotationlib` 模块。创建最小 stub 让 typeshed 引用链不中断。复用项目已有的 `typings/` 模式（dishka、opentelemetry）。

### Fix 3：修复 `pyright.tests.json`

**3a. 补全 extraPaths** — 与主配置保持一致，添加全部 7 个包：

```json
"extraPaths": [
    "packages/kernel/src",
    "packages/engine/src",
    "packages/infra/src",
    "packages/data/src",
    "packages/analytics/src",
    "packages/app/src",
    "interfaces/src"
]
```

**3b. Python 版本对齐** — `"3.12"` → `"3.13"`

### Fix 4：缓存策略优化

**文件**：`scripts/type.py`

- 默认不清除缓存，启用增量检查
- 新增 `--clean` 参数按需全量清理
- 更新 `pixi.toml` 的 `type-all` 命令保持原有行为

**文件**：`.gitignore`

- 添加 `.pyright_cache/` 和 `.basedpyright/`

## 实施步骤

1. 修改 `pyproject.toml`：添加 `venvPath` + `venv`
2. 创建 `typings/annotationlib.pyi`
3. 修复 `pyright.tests.json`：补全 extraPaths + Python 版本
4. 修改 `scripts/type.py`：条件化缓存清理
5. 更新 `.gitignore`
6. 运行 `pixi run -e dev check` 验证
