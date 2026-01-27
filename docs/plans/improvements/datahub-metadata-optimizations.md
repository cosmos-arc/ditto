# DataHub Metadata 域优化改进

> **来源:** PR #42 代码审查
> **审查日期:** 2026-01-27
> **优先级:** Medium（非阻塞改进）

**目标:** 优化 DataHub Metadata 域的性能、错误处理和用户体验

---

## Important 级别改进

### 1. IdentityStore 批量查询性能优化

**文件:** `packages/datahub/src/ditto_datahub/domains/metadata/identity/identity_store.py:106-147`

**问题:** `resolve_sids_batch()` 当前循环调用 `resolve_sid()`，存在 N+1 查询问题

**当前实现:**
```python
def resolve_sids_batch(
    self,
    src_codes: list[str],
    source: str = "tushare",
    asof: str | None = None,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for code in src_codes:  # N+1 查询问题
        sid = self.resolve_sid(code, source, asof)
        if sid:
            result[code] = sid
    return result
```

**优化方案:**
```python
def resolve_sids_batch(
    self,
    src_codes: list[str],
    source: str = "tushare",
    asof: str | None = None,
) -> dict[str, int]:
    """批量解析 src_codes 到 sids（使用单次 SQL 查询）。"""
    if not src_codes:
        return {}

    # 使用 IN 子句批量查询
    placeholders = ",".join("?" * len(src_codes))
    if asof:
        sql = f"""
            SELECT src_code, sid FROM identity_mapping
            WHERE source = ? AND src_code IN ({placeholders})
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY effective_from DESC
        """
        params = [source, *src_codes, asof, asof]
    else:
        sql = f"""
            SELECT src_code, sid FROM identity_mapping
            WHERE source = ? AND src_code IN ({placeholders})
              AND effective_to IS NULL
        """
        params = [source, *src_codes]

    rows = self.fetchall(sql, params)

    # 处理结果（保留每个 src_code 的最新记录）
    result: dict[str, int] = {}
    for row in rows:
        if row["src_code"] not in result:
            result[row["src_code"]] = int(row["sid"])

    return result
```

**影响:**
- 大批量查询时性能提升显著（100 个代码从 100 次查询降至 1 次）
- 减少数据库连接开销

---

### 2. Industry Stores 错误处理增强

**文件:**
- `packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_basic_store.py`
- `packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_mapping_store.py`

**问题:** 缺少数据库连接失败、约束违反等异常处理

**优化方案:**
```python
from ditto_foundation import logger

class IndustryBasicStore(SQLiteStore):
    @traced("data.industry.register")
    def register(self, industry: IndustryBasic) -> None:
        """注册行业信息."""
        try:
            self.execute(
                """INSERT OR REPLACE INTO industry_basic
                (industry_id, industry_name, industry_level, parent_id, is_active)
                VALUES (?, ?, ?, ?, ?)""",
                [
                    industry.industry_id,
                    industry.industry_name,
                    industry.industry_level,
                    industry.parent_id,
                    industry.is_active,
                ],
            )
            logger.info(
                "industry.registered",
                industry_id=industry.industry_id,
                industry_name=industry.industry_name,
            )
        except sqlite3.IntegrityError as e:
            logger.error(
                "industry.register_failed",
                industry_id=industry.industry_id,
                error=str(e),
            )
            raise
        except sqlite3.DatabaseError as e:
            logger.error(
                "industry.database_error",
                industry_id=industry.industry_id,
                error=str(e),
            )
            raise
```

**影响:**
- 更好的错误可观测性
- 便于排查生产问题

---

### 3. IdentityStore.register() 去重处理

**文件:** `packages/datahub/src/ditto_datahub/domains/metadata/identity/identity_store.py:183-246`

**问题:** 当前实现可能因重复注册引发异常

**优化方案:**
```python
@traced("data.identity.register")
def register(
    self,
    sid: int,
    src_code: str,
    source: str = "tushare",
    effective_from: str | None = None,
    is_primary: bool = True,
) -> None:
    """注册 identity_mapping 记录."""
    effective_from = effective_from or str(pl.Date.today())

    try:
        # 失效旧记录
        self.execute(
            """UPDATE identity_mapping
            SET effective_to = ?
            WHERE sid = ? AND source = ? AND effective_to IS NULL""",
            [effective_from, sid, source],
        )

        # 插入新记录
        self.execute(
            """INSERT INTO identity_mapping
            (sid, source, src_code, effective_from, is_primary)
            VALUES (?, ?, ?, ?, ?)""",
            [sid, source, src_code, effective_from, is_primary],
        )

        logger.info(
            "identity.registered",
            sid=sid,
            src_code=src_code,
            source=source,
        )
    except sqlite3.IntegrityError as e:
        logger.error(
            "identity.register_failed",
            sid=sid,
            src_code=src_code,
            error=str(e),
        )
        raise
```

**影响:**
- 更健壮的错误处理
- 更好的可观测性

---

## Minor 级别改进

### 4. 类型标注优化

**文件:** `packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_basic_store.py:50`

**当前:**
```python
params: list[object]
```

**优化:**
```python
params: list[str | int | bool | None]
```

---

### 5. 文档语言统一

**问题:** 代码中英文 docstring 混用

**优化方案:** 统一使用中文（符合项目规范）

---

### 6. 迁移指南

**文件:** `packages/datahub/README.md`

**新增章节:**
```markdown
## 迁移指南

### 从旧 Store 迁移到 Metadata 域

#### SecurityStore
**旧导入:**
```python
from ditto_datahub.stores import SecurityStore
```

**新导入:**
```python
from ditto_datahub.domains.metadata.security import SecurityStore
```

#### CalendarStore
**旧导入:**
```python
from ditto_datahub.stores import CalendarStore
```

**新导入:**
```python
from ditto_datahub.domains.metadata.calendar import CalendarStore
```

#### 使用 MetadataQueryService（推荐）
```python
from ditto_datahub.domains.metadata import MetadataQueryService

# 通过 DataHub 访问
sid = datahub.metadata.resolve_sid("600000.SH", source="tushare")
df = datahub.metadata.get_securities(sids=[sid])
```
```

---

### 7. Calendar Store 缓存配置

**文件:** `packages/datahub/src/ditto_datahub/domains/metadata/calendar/calendar_store.py`

**优化:** 将缓存大小作为可配置参数

```python
class CalendarStore(SQLiteStore):
    def __init__(
        self,
        db_path: Path,
        cache_enabled: bool = True,
        cache_size: int | None = None,  # None 表示全量缓存
    ) -> None:
        """初始化 CalendarStore.

        Args:
            db_path: 数据库路径
            cache_enabled: 是否启用内存缓存
            cache_size: 缓存条目数量（None 表示全量缓存，约 7500 条/1MB）
        """
        super().__init__(db_path)
        self._cache_enabled = cache_enabled
        self._cache_size = cache_size
        self._cache: DataCache[pl.DataFrame] | None = None
```

---

## 实施计划

| 任务 | 优先级 | 预计工作量 | 依赖 |
|------|--------|-----------|------|
| 1. IdentityStore 批量查询优化 | High | 2h | 无 |
| 2. Industry Stores 错误处理 | Medium | 3h | 无 |
| 3. IdentityStore.register() 去重 | Medium | 1h | 无 |
| 4. 类型标注优化 | Low | 1h | 无 |
| 5. 文档语言统一 | Low | 2h | 无 |
| 6. 迁移指南 | Low | 1h | 无 |
| 7. Calendar 缓存配置 | Low | 2h | 无 |

**总计:** 约 12 工时

---

## 验收标准

- [ ] 批量查询性能提升 >= 50%（100 个代码）
- [ ] 所有 Store 错误处理完整
- [ ] 迁移指南文档完整
- [ ] Pyright strict 通过
- [ ] 测试覆盖率保持 >= 80%

---

## 相关资源

- **原始 PR:** https://github.com/cosmos-arc/ditto/pull/42
- **实施计划:** [2026-01-27-datahub-phase1-metadata.md](../plans/2026-01-27-datahub-phase1-metadata.md)
- **DataHub README:** [packages/datahub/README.md](../../packages/datahub/README.md)
