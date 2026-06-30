# 修复 PR#66 代码审查 noqa 违规

## 概述
- Sprint: PR#66 follow-up | Phase: noqa 清零
- 创建: 2026-05-31
- 完成: 2026-05-31
- 状态: ✅ 全部完成
- 关联: PR#66 代码审查 5 个高置信度问题（评分均 ≥ 80）

## 技术方案

### 问题清单与修复策略

| # | 规则 | 文件 | 评分 | 策略 |
|---|------|------|------|------|
| 1 | PLR0913 | `backtest_audit.py` | 90 | 提取 `ArtifactPersistConfig` 冻结数据类 |
| 2 | PLW0603 | `dataset_registry.py` | 90 | 模块级闭包单例替代 `global` |
| 3 | PLW0603 | `catalog/metadata.py` | 100 | 模块级闭包单例替代 `global` |
| 4 | S608 | `sqlite_store.py` | 90 | 补充必需的注释说明 |
| 5 | D105 | `metadata.py` + `sqlite_journal.py` | 85 | 为 magic method 补充 docstring |

### 设计决策

**Q1: 为什么用闭包单例而非 noqa-ignore.md 推荐的类属性单例？**

noqa-ignore.md 推荐的 `SettingsManager` 类属性模式适合有状态服务。
但 `default_dataset_registry()` 和 `default_dataset_metadata()` 的本质是
**无副作用的惰性初始化**（纯数据工厂 + 缓存），引入一个 Manager 类会：
- 产生不必要的类层级
- 破坏现有的函数式调用风格（`default_dataset_registry()` → `DatasetRegistryManager.get_instance().get_registry()`）
- 调用方全部需要修改

闭包单例保持了 API 不变（仍为函数调用），同时消除了 `global` 语句：
```python
# 闭包单例模式
def default_dataset_registry() -> DatasetRegistry:
    if default_dataset_registry._cache is not None:  # type: ignore[attr-defined]
        return default_dataset_registry._cache       # type: ignore[attr-defined]
    registry = _build_registry()
    default_dataset_registry._cache = registry       # type: ignore[attr-defined]
    return registry
default_dataset_registry._cache: DatasetRegistry | None = None
```

> **注意**：上述模式引入 `# type: ignore[attr-defined]`，同样违反 noqa 零容忍。
> 因此采用**函数属性 + 类型存根**方案（见 Task 2/3 详细描述），通过 `cast` 避免 type: ignore。

最终方案：使用**模块级变量 + 函数参数默认值**模式：
```python
_REGISTRY_CACHE: DatasetRegistry | None = None

def default_dataset_registry(
    _cache: list[DatasetRegistry | None] = [None],  # noqa: RUF012
) -> DatasetRegistry:
    if _cache[0] is not None:
        return _cache[0]
    registry = _build_registry()
    _cache[0] = registry
    return registry
```

不，这也有 RUF012。最终采用最简方案：**模块级 `_cache` 变量 + 非 global 赋值**。
Python 模块级变量的赋值不需要 `global` 关键字，只要不重新绑定名称即可。
使用可变容器包装来绕过：

```python
_registry_cache: list[DatasetRegistry | None] = []

def default_dataset_registry() -> DatasetRegistry:
    if _registry_cache:
        return _registry_cache[0]
    registry = _build_registry()
    _registry_cache.append(registry)
    return registry
```

这是最干净的方案：无 `global`、无 `# noqa`、无 `# type: ignore`、API 不变。

**Q2: `persist_artifact` 参数过多如何拆分？**

从 `backtest_process.py` 调用方可以看到，参数来源于两个来源：
- `self._config`（strategy_id, initial_cash, rebalance_freq）
- `self._options`（artifact_service, artifact_dir, display_map）
- 调用上下文（run_id, report, manifest）
- 固定值（write_fn）

提取为两个配置数据类：
```python
@dataclass(frozen=True)
class ArtifactPersistContext:
    """调用上下文（每次调用不同）。"""
    run_id: str
    report: BacktestReport
    manifest: RunManifest | None = None

@dataclass(frozen=True)
class ArtifactPersistConfig:
    """持久化配置（BacktestService 级别不变）。"""
    strategy_id: str
    initial_cash: float
    rebalance_freq: str
    artifact_service: StrategyArtifactService
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None
    write_fn: Callable[..., dict[str, Path]] = write_backtest_artifacts
```

函数签名变为 `persist_artifact(ctx: ArtifactPersistContext, config: ArtifactPersistConfig) -> None`，
参数从 11 个降至 2 个。

---

## 任务清单

### Task 1: 提取 `ArtifactPersistConfig` 消除 PLR0913 `[M]`

- 验收: `persist_artifact` 签名 ≤ 3 个参数，无 `# noqa`
- 文件:
  - `packages/application/src/ditto_application/processes/execution/backtest_audit.py`
  - `packages/application/src/ditto_application/processes/execution/backtest_process.py`
- 步骤:
  1. 在 `backtest_audit.py` 新增 `ArtifactPersistContext` 和 `ArtifactPersistConfig` 冻结数据类
  2. 修改 `persist_artifact()` 签名为 `(ctx, config) -> None`
  3. 更新 `backtest_process.py:399-419` 的调用方 `_persist_artifact()`
  4. 更新 `__all__` 导出新数据类
  5. 验证现有测试通过
- 测试: 现有测试应全部通过（纯重构，行为不变）

### Task 2: 消除 `dataset_registry.py` 的 global 语句 `[S]`

- 验收: 无 `global` 语句，无 `# noqa`，API 不变
- 文件:
  - `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- 步骤:
  1. 将 `_default_registry: DatasetRegistry | None = None` 改为 `_registry_cache: list[DatasetRegistry | None] = []`
  2. 重写 `default_dataset_registry()` 使用 `_registry_cache` 列表缓存
  3. 删除 `global _default_registry  # noqa: PLW0603`
- 测试: 现有 `test_dataset_registry_unit.py` 应全部通过

### Task 3: 消除 `catalog/metadata.py` 的 global 语句 `[S]`

- 验收: 无 `global` 语句，无 `# noqa`，API 不变
- 文件:
  - `packages/data/src/ditto_data/catalog/metadata.py`
- 步骤:
  1. 将 `_cached_metadata: dict[str, DatasetMetadata] | None = None` 改为 `_metadata_cache: list[dict[str, DatasetMetadata] | None] = []`
  2. 重写 `default_dataset_metadata()` 使用 `_metadata_cache` 列表缓存
  3. 删除 `global _cached_metadata  # noqa: PLW0603`
- 测试: 现有 `test_metadata_unit.py` 应全部通过

### Task 4: 补充 S608 注释 `[S]`

- 验收: 所有 `# noqa: S608` 后附带注释说明
- 文件:
  - `packages/data/src/ditto_data/storage/base/sqlite_store.py`
- 步骤:
  1. 第 205 行: `# noqa: S608` → `# noqa: S608 - dataset 是受控的表名`
  2. 第 276 行: `# noqa: S608` → `# noqa: S608 - table 是受控的表名`
- 测试: 无需新增测试

### Task 5: 消除 D105 noqa — 为 magic method 补充 docstring `[S]`

- 验收: 无 `# noqa: D105`，magic method 有 docstring
- 文件:
  - `packages/data/src/ditto_data/catalog/metadata.py`
  - `packages/execution/src/ditto_execution/orders/sqlite_journal.py`
- 步骤:
  1. `catalog/metadata.py:223` — `__post_init__` 添加 docstring `"验证域字段合法性。"`
  2. `sqlite_journal.py:112` — `__enter__` 添加 docstring `"进入上下文管理器。"`
  3. `sqlite_journal.py:115` — `__exit__` 添加 docstring `"退出上下文管理器，关闭数据库连接。"`
- 测试: 无需新增测试

---

## 执行顺序

```
Task 4 (S608 注释)  ─┐
Task 5 (D105 docstr) ─┤── 并行（互不依赖）
Task 2 (global→cache)─┤
Task 3 (global→cache)─┤
                      │
Task 1 (PLR0913 拆分)─┘── 最后执行（涉及接口变更）
```

## 验证

所有任务完成后运行：

```bash
# noqa 零容忍验证
git grep "# noqa" packages/*/src | grep -v "S608\|S108\|S110"
# 预期：无输出

# global 语句零容忍验证
git grep "^global " packages/*/src
# 预期：无输出

# type: ignore 零容忍验证
git grep "# type: ignore" packages/*/src
# 预期：无输出

# 完整 CI 验证
pixi run -e dev check
```
