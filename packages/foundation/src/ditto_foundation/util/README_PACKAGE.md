# util

> 通用工具函数库，提供文件操作、哈希计算等基础设施支持

## 一、核心功能

### 1.1 工具函数

| 函数 | 功能 | 用途 |
|------|------|------|
| `atomic_write()` | 原子写入 Parquet 文件 | 确保数据写入完整性 |
| `file_md5()` | 计算文件 MD5 哈希 | 数据完整性校验、变更检测 |

## 二、架构定位

```
┌─────────────────────────────────────────────────┐
│           util（通用工具函数）                    │
└─────────────────┬───────────────────────────────┘
                  │
                  ↓ 被调用
┌─────────────────────────────────────────────────┐
│    stores, repositories, services, engines       │
└─────────────────────────────────────────────────┘
```

- **层级**：基础设施层
- **依赖**：外部库（polars）
- **职责**：提供可复用的工具函数

## 三、目录结构

```
util/
├── __init__.py    # 导出 atomic_write, file_md5
└── io.py          # IO 相关工具函数
```

## 四、关键模块说明

### 4.1 atomic_write()

**功能**：原子写入 Parquet 文件

**原理**：
1. 先写入临时文件（`.tmp` 后缀）
2. 写入完成后，原子性地重命名为目标文件

**好处**：
- 避免写入过程中的数据损坏
- 确保读取者只能看到完整的文件
- 写入失败时自动回滚

```python
from ditto_foundation.util import atomic_write
from pathlib import Path
import polars as pl

df = pl.DataFrame({
    "symbol": ["510300.SH"],
    "trade_date": ["20240102"],
    "close_price": [4.55]
})

# 原子写入
atomic_write(df, Path("./data/bars/2024/202401.parquet"))
```

### 4.2 file_md5()

**功能**：计算文件的 MD5 哈希值

**特点**：
- 分块读取，适用于大文件
- 返回 32 位十六进制字符串

```python
from ditto_foundation.util import file_md5
from pathlib import Path

checksum = file_md5(Path("./data/bars/2024/202401.parquet"))
print(checksum)  # 输出: "3a7bd3e2360a..."
```

**应用场景**：
- 数据完整性校验
- 文件变更检测
- 缓存失效判断

## 五、注意事项

### 5.1 atomic_write 使用

```python
# ✅ 正确：使用 Path 对象
atomic_write(df, Path("./data/output.parquet"))

# ✅ 正确：传入字符串会自动转换为 Path
atomic_write(df, "./data/output.parquet")

# ❌ 错误：目标目录必须可写
atomic_write(df, "/root/protected/output.parquet")  # 可能失败
```

### 5.2 MD5 哈希特点

- **确定性**：相同文件总是产生相同的哈希值
- **不可逆**：无法从哈希值还原原始数据
- **碰撞概率低**：不同文件产生相同哈希的概率极低
- **不适用于加密**：仅用于完整性校验

### 5.3 分块读取

`file_md5()` 使用 8KB 分块读取，避免大文件一次性加载到内存：

```python
# 8KB 分块，适用于任意大小的文件
for chunk in iter(lambda: f.read(8192), b""):
    md5.update(chunk)
```

### 5.4 压缩格式

`atomic_write()` 默认使用 `zstd` 压缩：

```python
# 内部实现
df.write_parquet(temp_path, compression="zstd")
```

`zstd` 提供良好的压缩率和速度平衡。

## 六、使用示例

### 6.1 数据写入与完整性校验

```python
from ditto_foundation.util import atomic_write, file_md5
from pathlib import Path
import polars as pl

# 准备数据
df = pl.DataFrame({
    "symbol": ["510300.SH", "510500.SH"],
    "trade_date": ["20240102", "20240102"],
    "close_price": [4.55, 6.78]
})

# 写入文件
output_path = Path("./data/bars/2024/202401.parquet")
atomic_write(df, output_path)

# 校验完整性
expected_md5 = "abc123..."  # 预期的 MD5
actual_md5 = file_md5(output_path)

if actual_md5 == expected_md5:
    print("数据完整性校验通过")
else:
    print("数据可能已损坏")
```

### 6.2 变更检测

```python
from ditto_foundation.util import file_md5, atomic_write
from pathlib import Path
import polars as pl

def update_if_changed(data: pl.DataFrame, path: Path) -> bool:
    """仅当数据变化时才更新文件."""
    new_md5 = file_md5(path) if path.exists() else ""

    # 计算新数据的 MD5（先写入临时文件）
    temp_path = path.with_suffix(".tmp")
    atomic_write(data, temp_path)
    new_data_md5 = file_md5(temp_path)

    if new_data_md5 != new_md5:
        # 数据已变化，执行更新
        temp_path.replace(path)
        return True
    else:
        # 数据未变化，删除临时文件
        temp_path.unlink()
        return False

# 使用
data = pl.DataFrame(...)
changed = update_if_changed(data, Path("./data/output.parquet"))

if changed:
    print("数据已更新")
else:
    print("数据未变化")
```

### 6.3 缓存管理

```python
from ditto_foundation.util import file_md5, atomic_write
from pathlib import Path
import polars as pl

class DataCache:
    """基于 MD5 的数据缓存."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = cache_dir / "index.json"

    def _get_cache_key(self, query_params: dict) -> str:
        """根据查询参数生成缓存键."""
        import json
        params_str = json.dumps(query_params, sort_keys=True)
        return hashlib.md5(params_str.encode()).hexdigest()

    def get(self, query_params: dict) -> pl.DataFrame | None:
        """获取缓存数据."""
        cache_key = self._get_cache_key(query_params)
        cache_path = self.cache_dir / f"{cache_key}.parquet"

        if cache_path.exists():
            return pl.read_parquet(cache_path)
        return None

    def put(self, query_params: dict, data: pl.DataFrame) -> None:
        """写入缓存."""
        cache_key = self._get_cache_key(query_params)
        cache_path = self.cache_dir / f"{cache_key}.parquet"
        atomic_write(data, cache_path)
```

### 6.4 错误处理

```python
from ditto_foundation.util import atomic_write, file_md5
from pathlib import Path
import polars as pl
import errno

def safe_write_with_retry(
    data: pl.DataFrame,
    path: Path,
    max_retries: int = 3
) -> bool:
    """带重试的安全写入."""
    for attempt in range(max_retries):
        try:
            atomic_write(data, path)
            # 验证写入完整性
            if path.exists():
                return True
        except OSError as e:
            if e.errno == errno.ENOSPC:
                print(f"磁盘空间不足，尝试 {attempt + 1}/{max_retries}")
            else:
                raise

    return False
```
