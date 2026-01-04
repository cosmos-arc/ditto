# 历史兼容代码清理计划

## 概述

全面清理项目中的历史兼容代码、遗留类和方法，简化代码库并移除技术债务。

**清理范围：**
1. DQ 系统遗留代码（DQChecker → DQEngine 迁移完成）
2. 配置系统环境变量兼容代码
3. FreezeManager MD5 兼容代码
4. Tushare Token 环境变量

## 状态：✅ 全部完成

所有任务已完成并通过测试验证。

---

## 任务 1：清理 DQ 系统遗留代码

### 1.1 删除核心文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `packages/datahub/src/ditto_datahub/runtime/dq_checker.py` | **删除** | 158行，已被 DQEngine 替代 |
| `packages/datahub/tests/unit/runtime/test_dq_checker.py` | **删除** | 243行测试，DQChecker 已废弃 |
| `packages/datahub/tests/unit/repositories/test_bars_dq_migration.py` | **删除** | 迁移测试已完成 |

### 1.2 清理 types.py

**文件：** `packages/datahub/src/ditto_datahub/types.py`

```python
# 删除第 47-56 行
@dataclass(frozen=True)
class DQResult:
    """Data quality check result (legacy, for runtime/dq_checker.py compatibility)."""
    ...
```

### 1.3 清理 hub.py

**文件：** `packages/datahub/src/ditto_datahub/hub.py`

```python
# 删除第 109-114 行
@cached_property
def dq_checker(self) -> DQChecker:
    """Data quality checker (deprecated: use dq_engine)."""
    from ditto_datahub.runtime.dq_checker import DQChecker
    return DQChecker()
```

### 1.4 清理 runtime/__init__.py

**文件：** `packages/datahub/src/ditto_datahub/runtime/__init__.py`

```python
# 删除第 4 行的导入
from .dq_checker import DQChecker

# 删除 __all__ 中的 "DQChecker" (第 13 行)
```

### 1.5 检查其他测试文件引用

根据 grep 结果，以下文件可能包含 DQChecker 引用，需要检查：

| 文件 | 检查项 |
|------|--------|
| `packages/datahub/tests/unit/repositories/test_bars.py` | 移除 DQChecker 相关导入/断言 |

---

## 任务 2：清理配置系统环境变量兼容代码

### 2.1 清理 DatabaseSettings

**文件：** `packages/foundation/src/ditto_foundation/config/settings.py`

**删除第 32-35 行：**
```python
# 私有属性用于从环境变量读取（向后兼容）
_duckdb_path_override: str = PrivateAttr(default="")
_sqlite_path_override: str = PrivateAttr(default="")
```

**简化 `__init__` 方法（删除第 36-45 行）：**
```python
# 删除整个 __init__ 方法，因为不再需要读取旧环境变量
def __init__(self, **kwargs: Any) -> None:
    """Initialize and read legacy environment variables."""
    super().__init__(**kwargs)
    # 从环境变量读取旧值（如果存在）
    ...
```

**简化 computed_field（第 48-66 行）：**
```python
# duckdb_path - 删除 if self._duckdb_path_override 检查
@computed_field
@property
def duckdb_path(self) -> Path:
    """DuckDB 数据库文件路径."""
    from ditto_foundation.config.paths import get_paths
    return get_paths().data_subdir("db/duckdb/ditto.duckdb")

# sqlite_path - 删除 if self._sqlite_path_override 检查
@computed_field
@property
def sqlite_path(self) -> Path:
    """SQLite 数据库文件路径."""
    from ditto_foundation.config.paths import get_paths
    return get_paths().data_subdir("db/sqlite/hub.sqlite")
```

### 2.2 清理 FileStorageSettings

**文件：** `packages/foundation/src/ditto_foundation/config/settings.py`

**删除第 117-121 行：**
```python
# 私有属性用于向后兼容（从环境变量读取）
_data_root_override: str = PrivateAttr(default="")
_log_root_override: str = PrivateAttr(default="")
_backup_root_override: str = PrivateAttr(default="")
_temp_root_override: str = PrivateAttr(default="")
```

**删除 `__init__` 方法（第 123-129 行）：**
```python
def __init__(self, **kwargs: Any) -> None:
    """Initialize and read legacy environment variables."""
    super().__init__(**kwargs)
    self._data_root_override = os.environ.get("DITTO_DATA_ROOT", "")
    ...
```

**简化 computed_field（第 131-172 行）：**
```python
# 所有 computed_field 删除 if self._xxx_override 检查
# 直接使用 XDGPaths
```

---

## 任务 3：清理 FreezeManager MD5 兼容代码

### 3.1 删除 MD5 计算方法

**文件：** `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**删除第 413-428 行：**
```python
def _compute_md5_checksum(self, file_path: Path) -> str:
    """计算文件的 MD5 checksum。"""
    ...
```

### 3.2 简化 _verify_files 方法

**文件：** `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**简化第 362-394 行：**
```python
# 删除 MD5 分支，只保留 SHA-256
def _verify_files(self, manifest: FreezeManifest) -> list[str]:
    errors: list[str] = []
    for rel_path, expected_checksum in manifest.files.items():
        file_path = self._data_root / rel_path
        if not file_path.exists():
            errors.append(f"File missing: {rel_path}")
            continue

        # 只使用 SHA-256 验证
        actual_checksum = self._compute_checksum(file_path)
        if actual_checksum != expected_checksum:
            errors.append(f"Checksum mismatch: {rel_path}")
    return errors
```

### 3.3 简化 _load_manifest 方法

**文件：** `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**简化第 451-478 行：**
```python
# 移除旧版本兼容逻辑，只支持 v2.0
def _load_manifest(self, path: Path) -> FreezeManifest:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # 不再支持旧版本格式
    version = data.get("version", "2.0")
    checksum_type = data.get("checksum_type", "sha256")

    # 如果是旧版本，抛出错误
    if version != "2.0" or checksum_type != "sha256":
        raise ValueError(
            f"Unsupported freeze manifest version '{version}' or checksum_type '{checksum_type}'. "
            "This version only supports SHA-256 checksums."
        )

    return FreezeManifest(
        freeze_id=data["freeze_id"],
        description=data["description"],
        created_at=data["created_at"],
        version=version,
        checksum_type=checksum_type,
        files=data["files"],
    )
```

### 3.4 更新文档字符串

**文件：** `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**更新第 19-24 行：**
```python
设计原则：
- Freeze = 轻量级可复现
- 使用 SHA-256 checksum 记录文件指纹
- 文件路径相对于 data_root
- Manifest 存储在 {data_root}/freezes/
```

---

## 任务 4：清理 Tushare Token 环境变量

### 4.1 移除 TUSHARE_TOKEN 环境变量支持

**文件：** `packages/datahub/src/ditto_datahub/sources/tushare/client.py`

**删除第 98-106 行：**
```python
# 4. Try TUSHARE_TOKEN env var (legacy)
if env_token := os.getenv("TUSHARE_TOKEN"):
    ...
```

**更新注释（第 40-44 行）：**
```python
# Priority order:
# 1. Provided token parameter
# 2. keyring (recommended)
# 3. ~/.ditto/secrets.toml (fallback)
```

### 4.2 检查测试文件

以下测试文件可能使用 TUSHARE_TOKEN 环境变量，需要检查并更新：

| 文件 | 检查项 |
|------|--------|
| `packages/datahub/tests/integration/sources/tushare/test_end_to_end.py` | 确认使用 keyring/secrets.toml |
| `packages/datahub/tests/unit/sources/tushare/test_client.py` | 确认测试方式 |
| `packages/datahub/tests/unit/sources/tushare/test_source.py` | 确认测试方式 |
| `apps/server/tests/conftest.py` | 确认测试配置 |

---

## 验证步骤

### 5.1 运行测试

```bash
# 运行所有测试确保没有破坏性变更
pixi run -e dev pytest

# 特别关注 DQ 相关测试
pixi run -e dev pytest packages/datahub/tests/unit/dq/

# 关注 FreezeManager 测试
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_freeze_manager.py

# 关注配置系统测试
pixi run -e dev pytest packages/foundation/tests/unit/
```

### 5.2 Lint 检查

```bash
pixi run -e dev pre-commit-run
```

### 5.3 类型检查

```bash
pixi run -e dev mypy
```

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 用户仍在使用旧环境变量 | 配置失效 | 运行测试前检查 CI 配置 |
| 旧版 freeze manifest 无法加载 | 数据丢失 | 用户确认不存在 MD5 格式 |
| DQChecker 下游依赖 | 导入失败 | grep 搜索确认无引用 |
| Tushare Token 配置 | 认证失败 | 检查测试和文档 |

---

## 文档更新

清理完成后，需要更新以下文档：

1. `packages/datahub/README.md` - 移除 DQChecker 引用
2. `packages/foundation/README.md` - 更新配置说明
3. 本计划文档 - 标记任务完成状态
