# Batch 1C: TradingRuntimeKernel 最小设计

> 创建：2026-05-25
> 基线：`docs/plans/2026-05-25-architecture-remediation-roadmap.md` Batch 1C
> 状态：已完成 ✅（2026-05-26）
> 依赖：Batch 1B（已完成）
> 业界参考：NautilusTrader NautilusKernel / ComponentState FSM

---

## 设计决策

### 1. RuntimeLifecycle FSM

参考 NautilusTrader `ComponentState`，15 个状态（8 稳态 + 7 过渡态）：

**稳态**：

| 状态 | 含义 | 典型场景 |
|------|------|---------|
| `PRE_INITIALIZED` | 已实例化，未配置 | 构造函数刚执行完 |
| `READY` | 已配置，可启动 | init/setup 完成 |
| `RUNNING` | 正常运行 | 回测执行中、paper 交易中 |
| `PAUSED` | 暂停（可恢复） | 用户主动暂停、盘间休市 |
| `STOPPED` | 已停止 | 回测完成、用户停止 |
| `DEGRADED` | 降级运行 | 数据源断开但继续 |
| `FAULTED` | 故障停机 | 不可恢复错误 |
| `DISPOSED` | 资源已释放 | 终态，不可逆 |

**过渡态**：

| 状态 | 触发 |
|------|------|
| `STARTING` | READY → RUNNING |
| `RESUMING` | PAUSED → RUNNING |
| `STOPPING` | RUNNING/PAUSED → STOPPED |
| `RESETTING` | STOPPED → READY |
| `DISPOSING` | → DISPOSED |
| `DEGRADING` | → DEGRADED |
| `FAULTING` | → FAULTED |

**合法转换矩阵**：

```
PRE_INITIALIZED → READY
READY → STARTING
STARTING → RUNNING | FAULTED
RUNNING → PAUSED | STOPPING | DEGRADING | FAULTING
PAUSED → RESUMING | STOPPING | FAULTING
RESUMING → RUNNING | FAULTED
STOPPING → STOPPED | FAULTED
STOPPED → RESETTING | DISPOSING
RESETTING → READY | FAULTED
DEGRADED → RESUMING | STOPPING | FAULTING
DEGRADING → DEGRADED | FAULTED
FAULTING → FAULTED
DISPOSING → DISPOSED
```

**容错**：任何过渡态均可因异常进入 FAULTED。

### 2. TradingRuntimeKernel Protocol

四要素：Clock + EventBus + Lifecycle + State

```python
@runtime_checkable
class TradingRuntimeKernel(Protocol):
    @property
    def clock(self) -> Clock: ...
    @property
    def event_bus(self) -> EventBus: ...
    @property
    def lifecycle(self) -> RuntimeLifecycle: ...
    @property
    def state(self) -> RuntimeSnapshot: ...
    def transition_to(self, target: RuntimeLifecycle) -> None: ...
```

**RuntimeSnapshot** — 不可变状态快照：

```python
@dataclass(frozen=True)
class RuntimeSnapshot:
    state: RuntimeLifecycle
    mode: str            # "backtest" | "paper" | "live"
    started_at: datetime | None
    error: str | None
```

### 3. 转换验证

`_validate_transition()` 纯函数放在 kernel，所有实现共享：

```python
def _validate_transition(current: RuntimeLifecycle, target: RuntimeLifecycle) -> None:
    """验证状态转换合法性，非法抛 RuntimeError。"""
    ...
```

---

## 执行计划

### B1C-1: TradingRuntimeKernel Protocol 定义 `[M]`

**文件**：
- `packages/kernel/src/ditto_kernel/runtime.py`（新建）
- `packages/kernel/src/ditto_kernel/__init__.py`（更新导出）

**内容**：
1. `RuntimeLifecycle` StrEnum（15 成员）
2. `RuntimeSnapshot` frozen dataclass
3. `_TRANSITIONS` 转换表 dict[RuntimeLifecycle, frozenset[RuntimeLifecycle]]
4. `_validate_transition()` 纯函数
5. `TradingRuntimeKernel` Protocol（@runtime_checkable）

**验收**：
- [x] Protocol 定义在 kernel（零依赖）
- [x] RuntimeLifecycle enum 在 kernel
- [x] 不引入新外部依赖
- [x] isinstance 检查通过

**测试**：
- [x] 单测：RuntimeLifecycle 枚举值正确
- [x] 单测：合法转换通过
- [x] 单测：非法转换抛 RuntimeError
- [x] 单测：RuntimeSnapshot frozen 不可变
- [x] 单测：TradingRuntimeKernel Protocol conformance

### B1C-2: BacktestRuntimeKernel 实现 `[M]`

**文件**：
- `packages/backtest/src/ditto_backtest/runtime.py`（新建）
- `packages/application/src/ditto_application/processes/execution/backtest_process.py`（改造）
- `packages/backtest/src/ditto_backtest/__init__.py`（更新导出）

**内容**：
1. `BacktestRuntimeKernel` 类：SimulatedClock + SimpleEventBus
2. 实现 `TradingRuntimeKernel` Protocol
3. backtest_process.py 委托 clock/event_bus 构造给 kernel
4. 添加 lifecycle 管理：PRE_INITIALIZED → READY → STARTING → RUNNING → STOPPING → STOPPED

**验收**：
- [x] `BacktestRuntimeKernel` 实现 `TradingRuntimeKernel` Protocol
- [ ] backtest_process.py 通过 kernel 构建 clock 和 event_bus（后续 PR）
- [x] 现有回测行为不变（regression test — 6834 passed）

**测试**：
- [x] 单测：BacktestRuntimeKernel 实现 Protocol
- [x] 单测：状态转换（PRE_INITIALIZED → READY → STARTING → RUNNING → STOPPING → STOPPED）
- [x] 单测：clock 返回 SimulatedClock
- [x] 单测：event_bus 返回 SimpleEventBus
- [ ] 集成测试：使用 BacktestRuntimeKernel 运行回测 → 结果与之前一致（后续 PR）

### B1C-3: PaperRuntimeKernel 实现 `[M]`

**文件**：
- `packages/execution/src/ditto_execution/broker/runtime.py`（新建）
- `packages/execution/src/ditto_execution/broker/__init__.py`（更新导出）

**内容**：
1. `PaperRuntimeKernel` 类：RealtimeClock + SimpleEventBus
2. 实现 `TradingRuntimeKernel` Protocol

**验收**：
- [x] `PaperRuntimeKernel` 实现 `TradingRuntimeKernel` Protocol
- [x] paper runtime 使用共享 kernel 原语

**测试**：
- [x] 单测：PaperRuntimeKernel 实现 Protocol
- [x] 单测：clock 返回 RealtimeClock（wall time）
- [x] 单测：event_bus 发布/订阅正常
- [x] 单测：状态转换正确

---

## 文件影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `packages/kernel/src/ditto_kernel/runtime.py` | 新建 | Protocol + Enum + Snapshot + 转换验证 |
| `packages/kernel/src/ditto_kernel/__init__.py` | 修改 | 新增导出 |
| `packages/kernel/tests/unit/test_runtime.py` | 新建 | Protocol + FSM 测试 |
| `packages/backtest/src/ditto_backtest/runtime.py` | 新建 | BacktestRuntimeKernel |
| `packages/backtest/tests/unit/test_runtime.py` | 新建 | BacktestRuntimeKernel 测试 |
| `packages/application/src/.../backtest_process.py` | 修改 | 委托给 BacktestRuntimeKernel |
| `packages/execution/src/.../broker/runtime.py` | 新建 | PaperRuntimeKernel |
| `packages/execution/tests/unit/broker/test_runtime.py` | 新建 | PaperRuntimeKernel 测试 |

## 验证

```bash
pixi run -e dev check           # lint + fmt + type + test --fast
pixi run -e dev arch-check      # 37 contracts kept
```
