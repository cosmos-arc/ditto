# apps/port 代码简化实施计划

## 执行摘要

基于 code-simplifier agent 的分析报告，将 12 个代码简化问题重组为 **4 个独立可执行的阶段**。

**关键指标：**
- 当前覆盖率：**93.41%** (超过 80% 阈值)
- 预计减少代码行数：**~200-250 行**
- 风险等级：**低-中** (高测试覆盖率保护)

**⚠️ 重要约束：破坏性修改允许**
- 无需向后兼容，无外部使用方
- 可直接调整依赖方的接入方式
- **禁止**添加兼容代码或遗留代码
- 删除旧代码时必须同步更新所有引用

---

## 阶段 1：CLI 命令工厂化重构

**优先级**: 🔴 高 | **风险**: 🟢 低 | **预估减少**: ~100 行

### 任务清单

- [ ] **1.1** 创建 `cli/commands/factory.py` - 实现命令工厂函数
- [ ] **1.2** 重构 `etf.py` 使用工厂模式 (-36 行)
- [ ] **1.3** 重构 `stock.py` 使用工厂模式 (-37 行)
- [ ] **1.4** 重构 `adj.py` 使用工厂模式 (-28 行)
- [ ] **1.5** 添加 `test_factory_unit.py` 单元测试
- [ ] **1.6** 运行验证测试

### 关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `cli/commands/factory.py` | 新建 | 命令工厂函数 |
| `cli/commands/etf.py` | 修改 | 使用工厂模式 |
| `cli/commands/stock.py` | 修改 | 使用工厂模式 |
| `cli/commands/adj.py` | 修改 | 使用工厂模式 |

### 工厂函数设计

```python
# cli/commands/factory.py
def create_daily_command(dataset: str, description: str) -> Callable:
    """创建 daily 命令的工厂函数。"""
    def command(ctx: typer.Context, date: str, force: bool) -> None:
        validate_date_format(date)
        ensure_executor(ctx)
        executor = ctx.obj["executor"]
        result = executor.ingest_daily(dataset, date, force)
        print_ingestion_result(result, ctx.obj["verbose"])
    command.__doc__ = description
    return command
```

### 验证命令

```bash
pixi run -e dev pytest -m integration tests/integration/cli/
pixi run -e dev pytest -m unit tests/unit/cli/
pixi run -e dev pytest --cov=ditto_port.cli --cov-report=term-missing
```

---

## 阶段 2：Flows 上下文管理器重构

**优先级**: 🔴 高 | **风险**: 🟡 中 | **预估减少**: ~50 行

### 任务清单

- [ ] **2.1** 创建 `jobs/flows/helpers.py` - 实现上下文管理器
- [ ] **2.2** 重构 `backfill.py` 使用上下文管理器 (-14 行)
- [ ] **2.3** 重构 `repair.py` 使用上下文管理器 (-30 行)
- [ ] **2.4** 重构 `daily.py` 使用上下文管理器 (-8 行)
- [ ] **2.5** 添加 `test_helpers_unit.py` 单元测试
- [ ] **2.6** 添加 `test_helpers_integration.py` 集成测试
- [ ] **2.7** 运行验证测试

### 关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `jobs/flows/helpers.py` | 新建 | 上下文管理器 |
| `jobs/flows/backfill.py` | 修改 | 2 处重复模式 |
| `jobs/flows/repair.py` | 修改 | 3 处重复模式 |
| `jobs/flows/daily.py` | 修改 | 1 处重复模式 |

### 上下文管理器设计

```python
# jobs/flows/helpers.py
@contextmanager
def create_ingestion_context(data_root: str, source: str = "tushare"):
    """创建摄取上下文，自动管理 DataHub 和 Coordinator 资源。"""
    hub = DataHub(data_root=data_root)
    try:
        data_source = hub.sources.get(source)
        coordinator = IngestionCoordinator(hub=hub, source=data_source, source_name=source)
        yield hub, coordinator
    finally:
        hub.close()
```

### 验证命令

```bash
pixi run -e dev pytest -m integration tests/integration/ingestion/flows/
pixi run -e dev pytest -m unit tests/unit/ingestion/flows/
pixi run -e dev pytest --cov=ditto_port.jobs.flows --cov-report=term-missing
```

---

## 阶段 3：中优先级优化

**优先级**: 🟡 中 | **风险**: 🟢 低-中 | **预估减少**: ~50 行

### 任务清单

- [ ] **3.1** 删除空 task wrapper 文件 (`t1_adj_factor.py`, `t1_bars.py`)
- [ ] **3.2** 提取结果统计辅助函数 (`_count_results`)
- [ ] **3.3** 简化 daily.py 任务依赖逻辑
- [ ] **3.4** 运行验证测试

### 关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `jobs/tasks/__init__.py` | 修改 | 添加别名导出 |
| `jobs/tasks/t1_adj_factor.py` | 删除 | 空文件 |
| `jobs/tasks/t1_bars.py` | 删除 | 空文件 |
| `services/ingestion/backfill.py` | 修改 | 提取辅助函数 |
| `jobs/flows/daily.py` | 修改 | 简化依赖逻辑 |

### 验证命令

```bash
grep -r "t1_adj_factor\|t1_bars" apps/port/src --include="*.py"  # 确认无残留引用
pixi run -e dev pytest -m integration tests/integration/ingestion/
pixi run -e dev pytest --cov=ditto_port --cov-report=term-missing
```

---

## 阶段 4：低优先级优化（可选）

**优先级**: 🟢 低 | **风险**: 🟢 低 | **预估减少**: ~25 行

### 任务清单

- [ ] **4.1** dataset config 工厂函数
- [ ] **4.2** security_mapper 可选列辅助函数
- [ ] **4.3** deploy.py 部署配置数据驱动

### 关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/ingestion/config/datasets.py` | 修改 | 配置工厂函数 |
| `services/ingestion/security_mapper.py` | 修改 | 可选列辅助函数 |
| `jobs/flows/deploy.py` | 修改 | 配置数据驱动 |

---

## 执行策略

### 推荐执行顺序

1. **阶段 1** (CLI 命令) - 独立性最高，风险最低
2. **阶段 2** (Flows) - 影响范围中等
3. **阶段 3** (中优先级) - 依赖阶段 2 完成
4. **阶段 4** (低优先级) - 可选

### 每阶段完成后

```bash
# 提交变更
git add apps/port/src ditto_port/tests
git commit -m "refactor(port): <阶段描述>"

# 验证测试
pixi run -e dev pre-commit-run
pixi run -e dev pytest --cov=ditto_port --cov-report=term-missing
```

### 回滚策略

如测试失败，使用 `git revert` 回滚：
```bash
git revert HEAD
```

---

## 跳过的问题

以下问题暂不处理：

- **问题 #5**: `coordinator.py` `_write_data` 策略模式重构 - 当前代码逻辑清晰，策略模式收益不高
- **问题 #8**: `middleware.py` 类型签名优化 - 符合 FastAPI 最佳实践
- **问题 #11**: 日志记录中的重复字段 - 可能影响可读性

---

## 总结

| 阶段 | 问题数量 | 代码减少 | 风险 |
|------|---------|---------|------|
| 阶段 1 | #1, #3 | ~100 行 | 🟢 低 |
| 阶段 2 | #2 | ~50 行 | 🟡 中 |
| 阶段 3 | #4, #6, #7 | ~50 行 | 🟢 低-中 |
| 阶段 4 | #9, #10, #12 | ~25 行 | 🟢 低 |

**总计**: 预计减少 **~225 行重复代码**，提高可维护性和可测试性。
