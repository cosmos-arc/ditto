# Ditto 依赖升级计划（2026-03-06）- 最终版 v2

## 0. 文档信息

- **状态**: ✅ 已完成
- **作者**: Claude
- **更新日期**: 2026-03-06
- **适用范围**: `pixi.toml` 全局依赖配置
- **升级策略**: 激进防御性升级 - 大版本稳定就升级
- **版本来源**: conda-forge（优先）+ PyPI（PyPI-only 包）

---

## 1. 升级策略

### 1.1 核心原则

> **如果大版本是稳定版，该升级就升级，除非有明确多个包直接的冲突**

### 1.2 风险等级定义

| 等级 | 图标 | 含义 | 处理方式 |
|------|------|------|---------|
| 低风险 | 🟢 | 稳定版，API 兼容 | 直接升级 |
| 中风险 | 🟡 | 需要验证 | 升级后验证 |
| 高风险 | 🔴 | 有冲突 | 权衡后决定 |

---

## 2. 最终变更汇总

### 2.1 删除的依赖（9 个）

| 分类 | 删除列表 | 原因 |
|------|---------|------|
| [dependencies] | numpy, pyarrow, aiohttp, requests, apscheduler | 未使用或间接依赖 |
| [pypi-dependencies] | - | - |
| [feature.dev] | pytest-benchmark, requests-mock, pandera, types-requests | 未使用 |

### 2.2 版本升级（11 个）

| 依赖 | 变更 | 说明 |
|------|------|------|
| prefect | `>=3.0,<4` → `>=3.4,<4` | 🔴 必须: 修复 Pydantic 兼容性 |
| granian | `>=1.0,<2` → `>=2.0,<3` | 🟢 2.x 稳定版 |
| dishka | `>=0.5,<1` → `>=1.8,<2` | 🟢 1.x 稳定版 |
| pytest | `>=8.0,<9` → `>=8.3,<9` | 🟢 小版本 |
| pytest-cov | `>=6.0,<7` → `>=6.1,<7` | 🟢 小版本 |
| pytest-asyncio | `>=0.24,<1` → `>=0.25,<1` | 🟢 小版本 |
| pytest-xdist | `>=3.5,<4` → `>=3.6,<4` | 🟢 小版本 |
| basedpyright | `>=1.15,<2` → `>=1.29,<2` | 🟢 小版本 |
| limits | 添加上限 `<6` | 🟡 跳过 3.15 是正常的 |
| inline-snapshot | 添加上限 `<1` | 🟢 规范化 |
| hypothesis | 添加上限 `<7` | 🟢 规范化 |

### 2.3 重新添加的依赖（1 个）

| 依赖 | 版本 | 原因 |
|------|------|------|
| socksio | `>=1.0,<2` | httpx SOCKS 代理支持（环境变量 ALL_PROXY 需要） |

---

## 3. 代码适配修改

### 3.1 StrEnum 升级（Python 3.11+）

新版 ruff 建议使用 `enum.StrEnum` 替代 `class X(str, Enum)`。

**修改文件（20 个枚举类）：**
- `apps/port/src/ditto_port/models/config.py`
- `packages/core/src/ditto_core/quality/golden.py`
- `packages/core/src/ditto_core/quality/spec.py`
- `packages/data/src/ditto_data/helpers/pit/policy.py`
- `packages/data/src/ditto_data/models/common.py`
- `packages/data/src/ditto_data/models/ingestion.py`
- `packages/data/src/ditto_data/models/strategy.py`
- `packages/data/src/ditto_data/models/trading.py`
- `packages/data/src/ditto_data/sources/normalization.py`
- `packages/data/src/ditto_data/stores/market/__init__.py`
- `packages/infra/src/ditto_infra/foundation/config/environment.py`
- `packages/infra/src/ditto_infra/foundation/config/initializer.py`
- `packages/infra/src/ditto_infra/services/notification/message.py`
- `packages/infra/tests/unit/config/test_initializer_unit.py`

### 3.2 Prefect 测试适配

Prefect 3.4+ 版本改变了测试行为，需要修改单元测试的 conftest.py：

**修改文件：**
- `apps/port/tests/unit/conftest.py`

**主要改动：**
1. 将 Prefect mock 移到模块级别（在测试模块导入前应用）
2. 添加 `MockTask` 类模拟 Prefect Task 接口（支持 `.submit()`, `.fn()` 等）
3. 过滤 Prefect 特有参数（`wait_for`, `return_state`, `refresh_cache`）

---

## 4. 验证结果

```bash
pixi run -e dev check
```

| 检查项 | 结果 |
|-------|------|
| Lint | ✅ All checks passed! |
| Format | ✅ 700 files left unchanged |
| Type | ✅ 0 errors, 0 warnings, 0 notes |
| Test | ✅ 1941 passed |
| Arch-check | ✅ 6 contracts kept, 0 broken |

---

## 5. 关键兼容性组合

| 组合 | 优先级 | 说明 |
|------|-------|------|
| **Prefect + Pydantic** | 🔴 最高 | Prefect 3.0-3.3 与 Pydantic 2.9+ 不兼容，必须升级 Prefect → 3.4+ |

---

## 6. 实施步骤

### 6.1 阶段 1：备份

```bash
cp pixi.lock pixi.lock.backup
```

### 6.2 阶段 2：修改 pixi.toml

按上表修改。

### 6.3 阶段 3：代码适配

```bash
# 自动修复 lint 问题
ruff check . --unsafe-fixes --fix
ruff check . --fix
```

### 6.4 阶段 4：安装验证

```bash
pixi clean
rm pixi.lock
pixi install
pixi install -e dev
pixi run -e dev check
```

---

## 7. 经验总结

### 7.1 SOCKS 代理依赖

如果环境变量中有 `ALL_PROXY=socks5://...`，httpx 需要 `socksio` 库支持。

### 7.2 Prefect 测试

Prefect 3.4+ 版本在单元测试中需要提前 mock 装饰器，否则会尝试连接 API 服务器导致超时。

### 7.3 StrEnum

Python 3.11+ 推荐使用 `enum.StrEnum` 替代 `class X(str, Enum)`。

---

## 8. 第二阶段升级（2026-03-06 审视后）

基于 conda-forge 和 PyPI 真实版本的严谨审视，进行以下升级：

### 8.1 版本升级（10 个）

| 依赖 | 原约束 | 新约束 | conda-forge/PyPI 最新版 | 理由 |
|------|--------|--------|------------------------|------|
| **polars** | `>=1.8,<2` | `>=1.9,<2` | 1.38.1 | 下限更新 |
| **duckdb** | `>=1.1,<2` | `>=1.3,<2` | 1.4.4 | 下限更新 |
| **pydantic** | `>=2.9,<3` | `>=2.10,<3` | 2.12.5 | 2.10.x 验证稳定 |
| **pydantic-settings** | `>=2.6,<3` | `>=2.10,<3` | 2.13.1 | 与 Pydantic 同步 |
| **tenacity** | `>=8.0,<9` | `>=9.0,<10` | 9.1.4 | 大版本更新 |
| **ruff** | `>=0.8,<1` | `>=0.9,<1` | 0.15.4 | 下限更新 |
| **pytest** | `>=8.3,<9` | `>=9.0,<10` | 9.0.2 | 大版本更新 |
| **pytest-cov** | `>=6.1,<7` | `>=7.0,<8` | 7.0.0 | 大版本更新 |
| **pytest-asyncio** | `>=0.25,<1` | `>=1.0,<2` | 1.3.0 | 大版本更新 |
| **faker** | `>=33,<40` | `>=40,<41` | 40.8.0 | 大版本更新 |

### 8.2 Pydantic 2.11.x 问题说明

**问题版本**: 2.11.0 - 2.11.4
**问题类型**: cloudpickle 序列化问题（[pydantic#8232](https://github.com/pydantic/pydantic/issues/8232)）
**修复版本**: 2.11.5+ 已修复
**当前使用**: 2.12.5 ✅（已修复）

### 8.3 验证结果

```bash
pixi run -e dev check
```

| 检查项 | 结果 |
|-------|------|
| Lint | ✅ All checks passed! |
| Format | ✅ 700 files left unchanged |
| Type | ✅ 0 errors, 0 warnings, 0 notes |
| Test | ✅ **1941 passed** in 27.62s |
| Arch-check | ✅ 6 contracts kept, 0 broken |

---

## 9. 依赖版本查询方式

### 9.1 conda-forge 查询

```bash
pixi search <package> -c conda-forge
```

### 9.2 PyPI 查询

```bash
curl -s "https://pypi.org/pypi/<package>/json" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['info']['version'])"
```

### 9.3 已安装版本查看

```bash
pixi list -e dev | grep <package>
```
