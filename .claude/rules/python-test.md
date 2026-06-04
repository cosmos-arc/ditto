---
paths:
  - tests/**/*.py
---

# 测试规范

## 测试组件栈

**必须使用以下组件，不得替换**：

| 组件 | 用途 | 使用场景 |
|------|------|----------|
| `pytest` | 测试框架 | 所有测试 |
| `polars.testing` | DataFrame断言 | 数据处理验证 |
| `polars.testing.parametric` | DataFrame生成 | Property测试 |
| `hypothesis` | Property-based测试 | 边界条件、数值计算 |
| `pytest-mock` | Mock框架 | 需要验证调用的场景 |
| `monkeypatch` | 简单替换 | 环境变量、属性替换 |
| `respx` | HTTP Mock | 外部API测试 |
| `inline-snapshot` | 快照测试 | 回测结果、API响应 |
| `pytest-cov` | 覆盖率 | CI集成 |

## 目录结构

```
packages/*/tests/
├── conftest.py
├── unit/           # 80% - 每次提交，完全 Mock，测原子功能
├── integration/    # 20% - CI运行，测"接缝"处（DAO、HTTP Client）
└── e2e/            # 端到端测试（仅 apps 包，验证完整管线）
```

**e2e 测试**仅存在于 `packages/apps/tests/e2e/`，验证完整数据管线（摄取→存储→查询→质量）。
命名约定：`test_*.py`（与单元测试相同，通过目录区分）。

**测试分类原则**：
- **单元测试**：完全 Mock，测试单个类的自身逻辑
- **集成测试**：真实组件，测试系统与外部的"接缝"处（DAO 写入数据库、HTTP Client 解析 API 响应）
- **Snapshot 测试**：验证策略输出与历史基线一致，命名 `test_*_snapshot.py`（位于 `integration/` 下，如 `packages/strategy/tests/integration/alpha/`）

### 🔴 强制要求：测试目录必须镜像源码目录结构

**核心原则**：测试目录结构必须与源码目录结构保持一致，任何源码目录重构必须同步更新测试目录。

#### 目录映射规则

```
src/ditto_platform/                         packages/platform/tests/unit/
├── foundation/               →          ├── foundation/
│   ├── cache/                →          │   ├── cache/
│   ├── config/               →          │   ├── config/
│   └── observability/        →          │   └── observability/

src/ditto_data/                       packages/data/tests/unit/
├── storage/                 →          ├── storage/
├── services/                →          ├── services/
├── sources/                 →          ├── sources/
├── quality/                 →          ├── quality/
├── models/                  →          ├── models/
└── runtime/                 →          └── runtime/

src/ditto_apps/                   packages/apps/tests/unit/
├── cli/                      →          ├── cli/
├── jobs/                     →          ├── jobs/
├── models/                   →          ├── models/
└── registry/                 →          └── registry/
```

#### 源码重构时的测试目录更新检查清单

**任何涉及以下操作的重构，必须同步更新测试目录**：

- [ ] 创建新源码目录 → 创建对应的测试目录
- [ ] 删除源码目录 → 删除对应的测试目录
- [ ] 重命名源码目录 → 重命名对应的测试目录
- [ ] 移动源码文件 → 移动对应的测试文件
- [ ] 合并源码目录 → 合并对应的测试目录

#### 禁止的目录结构模式

| ❌ 禁止模式 | ✅ 正确模式 | 原因 |
|-----------|-----------|------|
| 测试文件散布在根目录 | 按源码模块分组 | 难以维护 |
| `utils/` 测试目录（源码无 utils） | 对应具体源码模块 | 镜像原则 |
| `test_observability_unit.py` 重复 | 使用唯一命名或子目录 | 避免 import 冲突 |
| `ingestion/` 测试（源码是 `services/ingestion/`） | `services/ingestion/` | 保持一致 |

#### 检测命令

**重构后必须运行**：

```bash
# 1. 检查测试收集是否正常（无 import 冲突）
pixi run -e dev pytest --collect-only -q 2>&1 | grep -i "error\|mismatch"

# 2. 验证目录结构一致性
python -c "
from pathlib import Path

def get_dirs(path):
    return {d.name for d in Path(path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}

src_dirs = get_dirs('packages/platform/src')
test_dirs = get_dirs('packages/platform/tests/unit')

missing = src_dirs - test_dirs
extra = test_dirs - src_dirs

if missing:
    print(f'❌ 缺失测试目录: {missing}')
if extra:
    print(f'⚠️  多余测试目录: {extra}')
if not missing and not extra:
    print('✅ 目录结构一致')
"
```

---

## 编写规则

### 命名

```python
# ✅ test_calculate_sharpe_ratio_returns_zero_when_std_is_zero
# ❌ test_sharpe
```

### AAA模式

```python
def test_xxx():
    # Arrange - 准备数据
    # Act - 执行代码
    # Assert - 验证结果
```

### 单一职责

每个测试只验证一个行为，不要在一个测试中验证多个场景。

### 禁止假测试（绝对禁止）

| 形式 | 状态 | 原因 |
|------|------|------|
| `assert True` | ❌ | 没有实际验证 |
| `assert False` | ❌ | 永远失败 |
| 空的 `pass` | ❌ | 无断言 |
| `assert result is not None` | ❌ | 过于宽泛 |

```python
# ✅ 正确：验证具体行为
assert result.status == "success"
assert result.count == 3

# ✅ 测试异常路径
with pytest.raises(ValueError, match="Invalid input"):
    function_with_invalid_input()
```

**检查命令**：
```bash
grep -r "assert True" tests/
grep -r "assert False" tests/
```

---

## 覆盖率要求

**项目覆盖率标准（统一 80%）**：

| 指标 | 要求 | 配置位置 |
|------|------|----------|
| 分支覆盖率 | >= 80% | `pyproject.toml`: fail_under = 80 |
| CI 阈值 | >= 80% | `.github/workflows/ci.yml`: `--cov-fail-under=80` |
| 本地阈值 | >= 80% | `pixi.toml` test-cov-xml: `--cov-fail-under=80` |
| 新增代码 | >= 85% | CI 自动检查 |

### 覆盖率检查流程

```bash
# 本地开发时快速检查
pytest tests/unit/ -m "not slow" --cov

# 提交前完整检查
pytest --cov --cov-report=html --cov-report=term-missing

# 查看 HTML 报告
open htmlcov/index.html
```

---

## 运行命令

```bash
# 本地开发 - 跳过慢速和外部测试
pixi run -e dev pytest tests/unit/ -m "not slow and not external"

# 快速检查
pixi run -e dev pytest tests/unit/ -x --ff

# 冒烟测试
pixi run -e dev pytest -m smoke

# CI完整测试（跳过external）
pixi run -e dev pytest -m "not external" --cov

# 集成测试
pixi run -e dev pytest -m integration

# PIT验证测试
pixi run -e dev pytest -m pit

# === 性能测量命令 ===
# 识别最慢的 20 个测试
pixi run -e dev pytest --durations=20

# 只测量单元测试性能
pixi run -e dev pytest tests/unit --durations=20

# 只测量集成测试性能
pixi run -e dev pytest tests/integration --durations=20

# 并行运行测试（加速）
pixi run -e dev pytest tests/unit -n auto

# 运行性能基准测试
pixi run -e dev pytest -m benchmark --benchmark-only
```

---

## 并发测试配置

**项目已配置 pytest-xdist 并发测试** (`-n auto`)：

**注意事项**：
- 测试必须独立，不能有共享状态
- 使用 `tmp_path` 而非固定路径
- 避免使用全局变量或单例

**预期提速**：2-4倍

---

## 测试隔离性

```python
# ✅ 正确：每个测试独立准备数据
def test_feature_a(store):
    store.write(sample_data_a)
    result = store.read("a")
    assert result == expected_a

def test_feature_b(store):
    store.write(sample_data_b)  # 独立准备
    result = store.read("b")
    assert result == expected_b

# ❌ 错误：依赖执行顺序
def test_feature_a(store):
    global shared_state = "a"  # 不要使用全局状态
```

---

## 代码审查检查清单

提交测试代码前，确认：

### 基础规范

- [ ] 测试命名清晰描述了被测行为
- [ ] 遵循 AAA 模式
- [ ] 每个测试只验证一个行为
- [ ] 使用 fixture 而非重复代码
- [ ] Mock 只用于外部依赖
- [ ] 浮点数比较使用容差
- [ ] 边界条件有测试覆盖
- [ ] 异常路径有测试覆盖
- [ ] 无 sleep/time.sleep 等待
- [ ] 无硬编码路径或环境依赖
- [ ] 无假测试（assert True、assert False、空 pass）
- [ ] 使用参数化测试减少重复

### 🔴 目录结构强制检查

- [ ] **测试目录镜像源码目录结构**
- [ ] **源码目录重构时同步更新测试目录**
- [ ] **无 import 冲突（同名测试文件）**
- [ ] **测试文件命名符合规范**（`_unit.py` / `_integration.py`）

**源码重构时额外确认**：
- [ ] 创建源码目录 → 创建对应测试目录
- [ ] 删除源码目录 → 删除对应测试目录
- [ ] 重命名源码目录 → 重命名对应测试目录
- [ ] 移动源码文件 → 移动对应测试文件
- [ ] 合并源码目录 → 合并对应测试目录

---

## 检测问题命令（提交前必跑）

```bash
# 假测试检测
grep -r "assert True" tests/          # 假测试检测
grep -r "assert False" tests/

# import 冲突检测
pytest --collect-only 2>&1 | grep "import mismatch"  # import冲突

# 目录结构一致性检测（源码重构后必跑）
python -c "
from pathlib import Path

def check_structure(src_path, test_path, name):
    src_dirs = {d.name for d in Path(src_path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}
    test_dirs = {d.name for d in Path(test_path).rglob('*') if d.is_dir() and '__pycache__' not in str(d)}

    missing = src_dirs - test_dirs
    extra = test_dirs - src_dirs

    if missing or extra:
        print(f'❌ {name} 目录结构不一致:')
        if missing:
            print(f'   缺失测试目录: {missing}')
        if extra:
            print(f'   多余测试目录: {extra}')
        return False
    return True

all_ok = True
all_ok &= check_structure('packages/platform/src', 'packages/platform/tests/unit', 'Platform')
all_ok &= check_structure('packages/data/src', 'packages/data/tests/unit', 'Data')
all_ok &= check_structure('packages/apps/src', 'packages/apps/tests/unit', 'Apps')

if all_ok:
    print('✅ 所有包目录结构一致')
"

# 应迁移到 pytest-mock
grep -r "from unittest.mock" tests/
grep -r "@patch" tests/
```

---

## 完整检查命令

```bash
pixi run -e dev check             # 开发时（lint + fmt + type + test --fast）
pixi run -e dev pre-commit-run    # 提交前（pre-commit hooks）
pixi run -e dev ci                # CI 完整（lint + fmt --check + type --all + test --cov-xml）
```

---

## 类型检查（BasedPyright）

**配置**：
- 源码：`pyproject.toml` [tool.basedpyright] 段（standard + strict 模式）
- 测试：`pyright.tests.json`（basic 模式，宽松）

```bash
pixi run -e dev type          # 源码检查（strict + warnings）
pixi run -e dev type --tests  # 测试检查（basic 模式）
pixi run -e dev type --all    # 完整检查（源码 + 测试）
```

---

> 高级测试主题（单元/集成测试边界、DataFrame/Mock/PIT/快照/异步/参数化测试、性能规范、禁止模式、inline-snapshot）详见 [python-test-advanced.md](python-test-advanced.md)。
