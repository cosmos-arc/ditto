# Ditto 代码质量改进计划 - Ruff 问题全面清理

**计划创建时间**: 2026-01-16
**目标分支**: feature/pyright-cleanup-batch-0
**计划状态**: 待批准

---

## 执行摘要

基于两个计划文档的验证和当前代码质量检测：
- `2026-01-16-comprehensive-quality-improvement.md` - ✅ 已完成
- `2026-01-15-noqa-cleanup-plan.md` - ✅ 已完成

**遗留问题**: Ruff 检测出 **19 个非豁免问题**需要解决：

| 优先级 | 类型 | 数量 | 说明 |
|--------|------|------|------|
| P1 | PLR0913（参数过多） | 6 处 | 函数接口设计问题 |
| P1 | C901（复杂度过高） | 1 处 | 可维护性问题 |
| P2 | PLR0911（返回语句过多） | 2 处 | 控制流复杂度 |
| P2 | S112（异常吞噬） | 1 处 | 错误处理 |
| P3 | S101（assert 使用） | 5 处 | 生产代码健壮性 |
| P3 | S324（MD5 使用） | 1 处 | 安全说明 |
| P3 | S104（网络绑定） | 1 处 | 安全说明 |

**关键约束**:
- 核心源码零容忍：不允许 `# noqa` 和 `# type: ignore`（除 S608/S108/S110）
- 无需向后兼容：可直接重构 API
- 所有测试必须通过

---

## Phase 1: 高优先级 - 参数过多与复杂度优化（P1）

### 任务 1.1: pipeline_store.py 重构（3 个问题）

**文件**: `packages/datahub/src/ditto_datahub/stores/pipeline_store.py`

**问题**:
- 第 79 行: `insert_run` - 13 个参数 (PLR0913)
- 第 163 行: `update_run` - 9 个参数 (PLR0913)，复杂度 13 (C901)

**解决方案**:

1. **创建配置对象**（在文件顶部）:
```python
@dataclass(frozen=True)
class _PipelineRunConfig:
    """Pipeline run 配置对象"""
    run_id: str
    task_name: str
    dataset_id: str
    year: int | None = None
    rows_read: int | None = None
    rows_written: int | None = None
    status: str = "running"
    error_message: str | None = None
    dq_passed: bool | None = None
    dq_fail_count: int = 0
    dq_warn_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None

@dataclass(frozen=True)
class _PipelineRunUpdate:
    """Pipeline run 更新配置对象"""
    run_id: str
    status: str | None = None
    error_message: str | None = None
    rows_read: int | None = None
    rows_written: int | None = None
    dq_passed: bool | None = None
    dq_fail_count: int | None = None
    dq_warn_count: int | None = None
    finished_at: datetime | None = None
```

2. **重构 insert_run**:
```python
def insert_run(self, config: _PipelineRunConfig) -> None:
    """Insert pipeline run record using config object."""
```

3. **重构 update_run**（提取辅助方法降低复杂度）:
```python
def _build_update_fields(self, update: _PipelineRunUpdate) -> tuple[list[str], list[Any]]:
    """构建 UPDATE 语句的字段和参数"""

def update_run(self, update: _PipelineRunUpdate) -> None:
    """Update pipeline run record with reduced complexity"""
    updates, params = self._build_update_fields(update)
    # ... 其余逻辑
```

**验证步骤**:
```bash
pixi run -e dev test packages/datahub/tests/unit/stores/test_pipeline_store_unit.py
ruff check packages/datahub/src/ditto_datahub/stores/pipeline_store.py
```

**更新调用方**（如果存在直接调用）:
- 搜索 `insert_run(` 并替换为配置对象
- 搜索 `update_run(` 并替换为配置对象

---

### 任务 1.2: security.py 参数封装

**文件**: `packages/datahub/src/ditto_datahub/repositories/security.py`

**问题**: 第 218 行: `register` - 8 个参数

**解决方案**:
```python
# 创建配置类（建议放在 models.py 或本文件顶部）
@dataclass(frozen=True)
class SecurityRegistration:
    """证券注册信息配置对象"""
    src_code: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None

def register(self, registration: SecurityRegistration) -> int:
    """Register a new security and allocate SID."""
```

**验证步骤**:
```bash
pixi run -e dev test packages/datahub/tests/unit/repositories/test_security_repository_unit.py
```

---

### 任务 1.3: security_store.py 参数封装

**文件**: `packages/datahub/src/ditto_datahub/stores/security_store.py`

**问题**: 第 495 行: `register` - 9 个参数

**解决方案**: 复用 `SecurityRegistration` 配置对象
```python
def register(self, registration: SecurityRegistration, sid: int) -> int:
    """Register a new security."""
```

---

### 任务 1.4: paths.py 参数封装 ✅

**文件**: `packages/foundation/src/ditto_foundation/config/paths.py`

**问题**: 第 37 行: `PathResolver.__init__` - 8 个参数

**解决方案**:
```python
@dataclass(frozen=True)
class EnvVarConfig:
    """环境变量配置"""
    ditto_env: str
    xdg_env: str

@dataclass(frozen=True)
class PlatformConfig:
    """平台相关配置"""
    platform: str
    unix_default: str
    default_windows_base: str = "D:\\data\\ditto"

@dataclass(frozen=True)
class AppConfig:
    """应用配置"""
    app_name: str
    subdir: str

@dataclass(frozen=True)
class PathResolverConfig:
    """路径解析器配置对象（组合内聚的小配置）"""
    env: EnvVarConfig
    platform: PlatformConfig
    app: AppConfig
    base_override: Path | None = None

class PathResolver:
    def __init__(self, config: PathResolverConfig) -> None:
        """初始化路径解析器"""
```

**验证步骤**: ✅ 已完成
```bash
pixi run -e dev test packages/foundation/tests/unit
# 23 passed
pixi run -e dev ruff check packages/foundation/src/ditto_foundation/config/paths.py
# All checks passed!
pixi run -e dev type packages/foundation/src/ditto_foundation/config/paths.py
# 0 errors, 0 warnings
```

**更新调用方**: ✅ 已完成 - `XDGPaths._get_path` 已更新

**提交**: `0a7439e` - refactor(foundation): 拆分 PathResolverConfig 为内聚的小 dataclass

---

### 任务 1.5: pipeline_store.py insert_dq_issue 参数封装

**文件**: `packages/datahub/src/ditto_datahub/stores/pipeline_store.py`

**问题**: 第 396 行: `insert_dq_issue` - 8 个参数

**解决方案**:
```python
@dataclass(frozen=True)
class DQIssueConfig:
    """数据质量问题配置对象"""
    run_id: str
    dataset: str
    table_name: str
    issue_type: str
    severity: str
    description: str
    affected_rows: int = 0
    details: str | None = None

def insert_dq_issue(self, config: DQIssueConfig) -> None:
    """Insert DQ issue record."""
```

---

## Phase 2: 中优先级 - 返回语句与异常处理（P2）

### 任务 2.1: coordinator.py 返回语句优化

**文件**: `apps/port/src/ditto_port/services/ingestion/coordinator.py`

**问题**:
- 第 53 行: `ingest_date` - 8 个返回语句 (PLR0911)
- 第 254 行: `_fetch_data` - 7 个返回语句 (PLR0911)

**解决方案**:

**重构 ingest_date**（提取辅助方法）:
```python
def ingest_date(self, dataset: str, trade_date: str, force: bool = False) -> IngestionResult:
    """摄取单个交易日数据"""
    if skip_result := self._check_should_skip(dataset, trade_date, force):
        return skip_result

    if not self._is_trading_day_for_dataset(dataset, trade_date):
        return self._create_skipped_result(dataset, trade_date, "非交易日, 跳过")

    return self._fetch_and_ingest(dataset, trade_date)

def _check_should_skip(self, dataset: str, trade_date: str, force: bool) -> IngestionResult | None:
    """检查是否应该跳过摄取"""

def _is_trading_day_for_dataset(self, dataset: str, trade_date: str) -> bool:
    """检查数据集是否需要交易日验证"""

def _fetch_and_ingest(self, dataset: str, trade_date: str) -> IngestionResult:
    """获取数据并执行摄取（统一错误处理）"""
```

**重构 _fetch_data**（简化分发逻辑）:
```python
def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
    """根据数据集类型调用对应的 Source 方法获取数据"""
    method_name = self._DATASET_METHODS.get(dataset)
    if method_name is None:
        raise ValueError(f"不支持的数据集: {dataset}")

    source_method = getattr(self._source, method_name, None)
    if source_method is None or not callable(source_method):
        raise ValueError(f"Source 方法不存在: {method_name}")

    return source_method(trade_date)
```

**验证步骤**:
```bash
pixi run -e dev test apps/port/tests -m integration
```

---

### 任务 2.2: models.py 异常处理细化

**文件**: `packages/datahub/src/ditto_datahub/dq/models.py`

**问题**: 第 250 行: 静默 continue，吞噬所有异常 (S112)

**解决方案**:
```python
# 重构后
try:
    if data and "dataset" in data:
        dataset_rules = DatasetRules(**data)
        datasets[dataset_rules.dataset] = dataset_rules
except (ValidationError, ValueError) as e:
    logger.warning("Invalid DQ config file, skipping", event="dq_config_invalid", file=str(config_file), error=str(e))
    continue
except yaml.YAMLError as e:
    logger.warning("Failed to parse YAML config, skipping", event="dq_config_parse_error", file=str(config_file), error=str(e))
    continue
```

---

## Phase 3: 低优先级 - Assert 与安全说明（P3）

### 任务 3.1: freeze_manager.py 类型收窄优化（S101 × 2）

**文件**: `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`

**问题**: 第 390、399 行使用 assert 进行类型收窄

**解决方案**: 重构返回类型
```python
def _try_single_file_mode(self, dataset: str) -> Checksums | None:
    """尝试单文件模式。成功返回 checksums，失败返回 None"""

def _try_partitioned_directory_mode(self, dataset: str) -> Checksums | None:
    """尝试分区目录模式。成功返回 checksums，失败返回 None"""

# 调用处重构
if checksums := self._try_single_file_mode(dataset):
    files.update(checksums)
```

---

### 任务 3.2: tushare/client.py 类型收窄优化（S101 × 2）

**文件**: `packages/datahub/src/ditto_datahub/sources/tushare/client.py`

**问题**: 第 72、89 行使用 assert 确保类型

**解决方案**:
```python
def _load_token_from_keyring(self) -> str | None:
    """从 keyring 加载 token"""
    if keyring is None:
        return None
    try:
        token = keyring.get_password("ditto", "tushare")
        if token and isinstance(token, str):
            return token
        return None
    except Exception as e:
        logger.debug("Keyring not available, skipping", error=str(e))
        return None
```

---

### 任务 3.3: ingestion_log.py 断言移除（S101 × 1）

**文件**: `packages/datahub/src/ditto_datahub/stores/ingestion_log.py`

**问题**: 第 148 行使用 assert 验证 UPSERT 返回值

**解决方案**:
```python
# 当前: assert row is not None, "..."
# 重构后:
if row is None:
    raise RuntimeError("UPSERT RETURNING should always return a row but got None")
```

---

### 任务 3.4: sql_engine.py MD5 安全说明（S324 × 1）

**文件**: `packages/datahub/src/ditto_datahub/runtime/sql_engine.py`

**问题**: 第 245 行使用 MD5 生成缓存键

**解决方案**: 添加详细安全说明注释
```python
# Generate cache key using MD5 hash
# 安全说明: 此处使用 MD5 仅用于缓存键生成（非安全用途）
# - 输入: 标准化的 SQL 查询字符串
# - 用途: 快速哈希以识别重复查询
# - 风险: 不涉及密码或敏感数据，MD5 碰撞对缓存场景影响可忽略
cache_key = hashlib.md5(normalized.encode()).hexdigest()
```

---

### 任务 3.5: settings.py 网络绑定说明（S104 × 1）

**文件**: `packages/foundation/src/ditto_foundation/config/settings.py`

**问题**: 第 61 行默认绑定 0.0.0.0（所有接口）

**解决方案**: 添加安全说明注释
```python
host: str = Field(
    default="0.0.0.0",
    description=(
        "服务器监听地址。"
        "安全说明: 0.0.0.0 表示监听所有网络接口，适用于容器化部署场景。"
        "生产环境应通过环境变量 SERVER_HOST 配置为具体地址或通过防火墙限制访问。"
    )
)
```

---

## 关键文件清单

### 修改文件
1. `packages/datahub/src/ditto_datahub/stores/pipeline_store.py` - 最高优先级
2. `packages/datahub/src/ditto_datahub/repositories/security.py`
3. `packages/datahub/src/ditto_datahub/stores/security_store.py`
4. `packages/foundation/src/ditto_foundation/config/paths.py`
5. `apps/port/src/ditto_port/services/ingestion/coordinator.py`
6. `packages/datahub/src/ditto_datahub/dq/models.py`
7. `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`
8. `packages/datahub/src/ditto_datahub/sources/tushare/client.py`
9. `packages/datahub/src/ditto_datahub/stores/ingestion_log.py`
10. `packages/datahub/src/ditto_datahub/runtime/sql_engine.py`
11. `packages/foundation/src/ditto_foundation/config/settings.py`

### 新增配置类
- `_PipelineRunConfig` - pipeline_store.py 内部类
- `_PipelineRunUpdate` - pipeline_store.py 内部类
- `DQIssueConfig` - pipeline_store.py 内部类
- `SecurityRegistration` - repositories/security.py 或独立 models.py
- `PathResolverConfig` - config/paths.py 顶部

---

## 验证方法

### 每个任务完成后执行
```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 相关单元测试
pixi run -e dev test --unit <package>/tests/unit
```

### 最终验证
```bash
# 完整检查
pixi run -e dev ci

# 统计剩余问题（排除 S608）
pixi run -e dev lint 2>&1 | grep -v "S608\|S108\|S110" | grep -E "PLR|C90|S101|S112|S324|S104" | wc -l
# 预期: 0
```

---

## 预估工作量

| Phase | 任务数 | 工作量 |
|-------|--------|--------|
| Phase 1 | 5 | 3-4 人日 |
| Phase 2 | 2 | 2-3 人日 |
| Phase 3 | 5 | 1-2 人日 |
| **总计** | **12** | **6-9 人日** |

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 配置对象引入破坏性变更 | 完整测试覆盖，无向后兼容要求 |
| 复杂度优化改变执行路径 | 保留原逻辑，仅提取辅助方法 |
| 类型收窄改变运行时行为 | 添加边界测试 |
| 调用方更新遗漏 | 使用 grep 搜索所有调用点 |
