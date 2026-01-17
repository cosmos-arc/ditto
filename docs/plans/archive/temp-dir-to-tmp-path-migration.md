# temp_dir Fixture 迁移到 tmp_path 计划

## 执行摘要

将 `temp_dir` 自定义 fixture 迁移到 pytest 内置的 `tmp_path` fixture。

| 指标 | 数值 |
|------|------|
| 受影响文件 | 6 个 |
| 受影响测试函数 | 25 个 |
| 风险等级 | 🟢 低 |
| 预估时间 | ~15 分钟 |

---

## 一、背景

### 当前实现

```python
# apps/port/tests/conftest.py:131-135
@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """临时目录fixture（已废弃，使用 pytest 内置 tmp_path）。"""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
```

### 目标

使用 pytest 内置的 `tmp_path` fixture，它提供：
- 自动清理
- 更好的类型提示
- pytest 标准实践
- 无需自定义代码

---

## 二、影响范围

### 文件清单

| 文件 | 测试数量 | 修改类型 |
|------|----------|----------|
| `apps/port/tests/conftest.py` | 1 (fixture 定义) | 删除 |
| `apps/port/tests/integration/cli/test_adj_commands.py` | 6 | 参数重命名 |
| `apps/port/tests/integration/cli/test_calendar_commands.py` | 2 | 参数重命名 |
| `apps/port/tests/integration/cli/test_etf_commands.py` | 6 | 参数重命名 |
| `apps/port/tests/integration/cli/test_stock_commands.py` | 6 | 参数重命名 |
| `apps/port/tests/integration/test_e2e.py` | 5 | 参数重命名 |

**总计**: 6 个文件，25 个测试函数

---

## 三、迁移策略

### 方案：别名过渡法（推荐）

**步骤 1**: 将 `temp_dir` 改为 `tmp_path` 的别名

```python
# apps/port/tests/conftest.py
@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """临时目录fixture（已废弃，使用 pytest 内置 tmp_path）。"""
    return tmp_path
```

**好处**:
- 最小化变更
- 所有测试立即兼容
- 可以逐步迁移

**步骤 2**: 逐文件迁移测试

```python
# 迁移前
def test_stock_daily_command(temp_dir: Path):
    result = runner.invoke(app, ["--data-root", str(temp_dir), ...])

# 迁移后
def test_stock_daily_command(tmp_path: Path):
    result = runner.invoke(app, ["--data-root", str(tmp_path), ...])
```

**步骤 3**: 删除 `temp_dir` fixture

---

## 四、执行计划

### 阶段 1：创建别名（必须）

**文件**: `apps/port/tests/conftest.py`

```diff
 @pytest.fixture
-def temp_dir() -> Generator[Path, None, None]:
-    """临时目录fixture（已废弃，使用 pytest 内置 tmp_path）。"""
-    with TemporaryDirectory() as tmpdir:
-        yield Path(tmpdir)
+def temp_dir(tmp_path: Path) -> Path:
+    """临时目录fixture（已废弃，使用 pytest 内置 tmp_path）。"""
+    return tmp_path
```

**验证**:
```bash
pixi run -e dev pytest apps/port/tests/integration/cli/ -v
```

---

### 阶段 2：迁移测试文件（可选）

#### 文件 1: test_adj_commands.py

```bash
sed -i 's/temp_dir: Path/tmp_path: Path/g' apps/port/tests/integration/cli/test_adj_commands.py
sed -i 's/str(temp_dir)/str(tmp_path)/g' apps/port/tests/integration/cli/test_adj_commands.py
```

#### 文件 2: test_calendar_commands.py

```bash
sed -i 's/temp_dir: Path/tmp_path: Path/g' apps/port/tests/integration/cli/test_calendar_commands.py
sed -i 's/str(temp_dir)/str(tmp_path)/g' apps/port/tests/integration/cli/test_calendar_commands.py
```

#### 文件 3: test_etf_commands.py

```bash
sed -i 's/temp_dir: Path/tmp_path: Path/g' apps/port/tests/integration/cli/test_etf_commands.py
sed -i 's/str(temp_dir)/str(tmp_path)/g' apps/port/tests/integration/cli/test_etf_commands.py
```

#### 文件 4: test_stock_commands.py

```bash
sed -i 's/temp_dir: Path/tmp_path: Path/g' apps/port/tests/integration/cli/test_stock_commands.py
sed -i 's/str(temp_dir)/str(tmp_path)/g' apps/port/tests/integration/cli/test_stock_commands.py
```

#### 文件 5: test_e2e.py

```bash
sed -i 's/temp_dir: Path/tmp_path: Path/g' apps/port/tests/integration/test_e2e.py
sed -i 's/str(temp_dir)/str(tmp_path)/g' apps/port/tests/integration/test_e2e.py
```

**每文件验证**:
```bash
pixi run -e dev pytest apps/port/tests/integration/cli/test_X_commands.py -v
```

---

### 阶段 3：删除旧 fixture（可选）

**文件**: `apps/port/tests/conftest.py`

```diff
-@pytest.fixture
-def temp_dir(tmp_path: Path) -> Path:
-    """临时目录fixture（已废弃，使用 pytest 内置 tmp_path）。"""
-    return tmp_path
```

**最终验证**:
```bash
pixi run -e dev pytest apps/port/tests/integration/ -v
```

---

## 五、验证清单

### 阶段 1 完成后

- [x] `temp_dir` 改为 `tmp_path` 别名
- [x] 所有 CLI 测试通过 (40 个)
- [x] 无 `TemporaryDirectory` 导入警告

### 阶段 2 完成后

- [x] 所有测试文件使用 `tmp_path`
- [x] 所有测试通过
- [x] 无 `temp_dir` 引用

### 阶段 3 完成后

- [x] `temp_dir` fixture 已删除
- [x] `TemporaryDirectory` 导入已删除
- [x] 所有测试通过

---

## 六、回滚策略

如果测试失败：

```bash
git checkout apps/port/tests/
```

---

## 七、执行选项

| 选项 | 操作 | 风险 |
|------|------|------|
| **A. 仅阶段 1** | 创建别名，保持现状 | 🟢 无 |
| **B. 阶段 1 + 2** | 创建别名 + 迁移测试 | 🟡 低 |
| **C. 全部** | 完整迁移 | 🟡 低 |

**推荐**: 选项 B - 既消除技术债务，又控制风险

---

## 八、相关文件

| 文件 | 操作 |
|------|------|
| `apps/port/tests/conftest.py` | 修改/删除 fixture |
| `apps/port/tests/integration/cli/test_adj_commands.py` | 重命名参数 |
| `apps/port/tests/integration/cli/test_calendar_commands.py` | 重命名参数 |
| `apps/port/tests/integration/cli/test_etf_commands.py` | 重命名参数 |
| `apps/port/tests/integration/cli/test_stock_commands.py` | 重命名参数 |
| `apps/port/tests/integration/cli/test_e2e.py` | 重命名参数 |

---

## 九、执行完成

**执行时间**: 2026-01-14

**结果**: ✅ 成功完成所有阶段（阶段 1 + 2 + 3）

**提交记录**:
- `0bd4a91` - refactor: 将 temp_dir fixture 改为 tmp_path 别名
- `b8e2c01` - refactor: 迁移 test_adj_commands.py 到 tmp_path
- `cf84b74` - refactor: 迁移 test_calendar_commands.py 到 tmp_path
- `a38587f` - refactor: 迁移 test_etf_commands.py 到 tmp_path
- `61b5a96` - refactor: 迁移 test_stock_commands.py 到 tmp_path
- `9d2a8ae` - refactor: 迁移 test_e2e.py 到 tmp_path
- `3b78805` - refactor: 删除 temp_dir fixture

**验证结果**:
- ✅ 40 个 CLI 测试全部通过
- ✅ lint + fmt + type 检查全部通过
- ✅ 1358 个单元测试通过（2 个预先存在的 hypothesis 超时失败）
- ✅ 无 `temp_dir` 引用残留
- ✅ `TemporaryDirectory` 导入已删除
