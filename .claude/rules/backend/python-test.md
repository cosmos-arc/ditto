---
paths: test/**/*.py
---

# Python Test Rules

## 核心原则
- **AAA 模式**: 每个测试遵循 Arrange-Act-Assert 结构
- **测试隔离**: 测试独立运行，禁止共享可变状态
- **镜像结构**: 测试文件与源码目录结构一一对应

## 目录结构
```
packages/{pkg}/
├── src/ditto_{pkg}/{child_pkg}/module.py
└── tests/
    ├── conftest.py          # 包级别 fixtures
    ├── unit/{child_pkg}/test_module.py
    ├── integration/{child_pkg}/test_module_integration.py
    └── fixtures/{child_pkg}/
```
- tests 目录下禁止创建 `__init__.py`
- 根目录 `tests/` 仅用于跨模块测试 (e2e/, perf/)

## 命名规范
- 文件: `test_{模块名}.py`
- 函数: `test_{被测对象}_{场景}_{预期结果}`
- 示例: `test_kill_switch_when_drawdown_exceeds_threshold_triggers_halt`

## 测试分类与 Marker
| 目录 | 必须 Marker | 允许真实依赖 |
|------|-------------|-------------|
| unit/ | 无 | ❌ 禁止 |
| integration/ | @pytest.mark.integration | ✅ 测试环境 |
| e2e/ | @pytest.mark.e2e | ✅ 受控环境 |
| perf/ | @pytest.mark.benchmark | ✅ |

## 外部依赖策略
**单元测试**: 必须使用 Mock/Fake
```python
# 推荐: 依赖注入 + Fake 实现
class FakePriceRepository:
    def get_prices(self, symbol): return fake_df

def test_strategy(fake_repo):
    strategy = Strategy(price_repo=fake_repo)
    assert strategy.generate_signals() is not None
```

**集成测试**: 使用真实测试依赖
```python
@pytest.mark.integration
def test_pit_loader_with_duckdb(tmp_path):
    db = setup_test_db(tmp_path)
    df = load_pit_data(as_of="2024-01-01", db_path=db)
    assert df["date"].max() <= "2024-01-01"
```

## 金融计算验证
```python
# 浮点数比较（精确到分）
assert actual == pytest.approx(expected, rel=1e-5, abs=1e-2)

# PIT 数据完整性
assert data["date"].max() <= as_of_date
```

## 异步测试
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_func()
    assert result is not None
```
- 异步测试内禁止调用 `asyncio.run()`
- 配置 `asyncio_mode = "auto"`

## 覆盖率要求
- 整体: ≥80% (CI 强制)
- 关键模块（风控、仓位）: ≥90%
- 启用分支覆盖率

## 禁止行为
- ❌ 单元测试中访问真实 HTTP/DB/API
- ❌ 仅测试 mock 调用行为
- ❌ 测试间共享可变状态
- ❌ tests 目录下创建 `__init__.py`
- ❌ 生产代码 import tests 包

## 技术栈
```
必须：pytest, pytest-cov, pytest-mock, pytest-asyncio
可选: pytest-benchmark, faker, hypothesis
禁止：非以上测试技术栈，如需要请沟通
```
