# Ditto AI 协作规范

**版本：v2.0 Final**

**日期：2025-12-08**

---

## 1. 文档目的

本文档定义了在 Ditto 项目中如何与 AI 编程助手（如 Claude、GitHub Copilot）高效协作的规范，确保：

1. AI 生成的代码符合项目架构和风格
2. AI 能快速理解项目上下文
3. 人机协作流程清晰高效
4. 代码质量有保障

---

## 2. AI 角色定义

### 2.1 AI 擅长的任务

| 任务类型 | 说明 | 示例 |
|----------|------|------|
| 代码实现 | 根据设计文档实现具体代码 | 实现 FactorEngine |
| 代码重构 | 改善代码结构和可读性 | 提取公共逻辑 |
| 测试编写 | 根据代码编写测试用例 | 单元测试、对齐测试 |
| 文档生成 | 根据代码生成文档 | API 文档、类型说明 |
| Bug 修复 | 根据错误信息定位修复 | 修复数据处理 bug |
| 代码解释 | 解释复杂代码逻辑 | 解释回测引擎流程 |

### 2.2 AI 不擅长的任务

| 任务类型 | 原因 | 建议处理方式 |
|----------|------|--------------|
| 架构决策 | 需要全局视角和业务理解 | 人工决策，AI 辅助分析 |
| 策略设计 | 需要金融领域知识和经验 | 人工设计，AI 辅助实现 |
| 参数调优 | 需要实验和迭代 | 人工主导，AI 辅助分析 |
| 数据核验 | 需要与外部数据源对比 | 人工核验 |
| 风控规则 | 涉及风险承受能力 | 人工决策 |

### 2.3 人机协作模式

```
人类：设计架构、定义接口、决策参数、核验结果
  │
  ▼
 AI：实现代码、编写测试、生成文档、修复 bug
  │
  ▼
人类：Review、测试、集成、部署
```

---

## 3. 提示词（Prompt）模板

### 3.1 代码实现任务

```markdown
## 任务：实现 [模块名称]

### 背景
[简要描述该模块在系统中的位置和作用]

### 设计参考
- 相关文档：[文档路径]
- 相关接口：[接口定义]

### 需求
1. [需求点1]
2. [需求点2]
3. [需求点3]

### 约束
- 编程语言：Python 3.11+
- 依赖限制：[允许使用的库]
- 风格要求：遵循项目代码规范

### 输入输出
- 输入：[描述输入]
- 输出：[描述输出]

### 示例
[提供具体的输入输出示例]

### 验收标准
- [ ] [标准1]
- [ ] [标准2]
```

### 3.2 Bug 修复任务

```markdown
## 任务：修复 [Bug 描述]

### 错误信息
```
[粘贴完整的错误堆栈]
```

### 复现步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

### 相关代码
```python
[粘贴相关代码片段]
```

### 期望行为
[描述正确的行为应该是什么]

### 实际行为
[描述实际观察到的行为]

### 可能的原因
[如果有推测的原因可以列出]
```

### 3.3 代码审查任务

```markdown
## 任务：审查代码

### 代码片段
```python
[粘贴待审查的代码]
```

### 审查重点
- [ ] 逻辑正确性
- [ ] 边界条件处理
- [ ] 错误处理
- [ ] 性能问题
- [ ] 代码风格
- [ ] PIT 安全（Point-in-Time）
- [ ] 涨跌停处理

### 上下文说明
[描述这段代码的用途和上下文]
```

### 3.4 测试编写任务

```markdown
## 任务：为 [模块名称] 编写测试

### 被测代码
```python
[粘贴被测试的代码]
```

### 测试要求
- 测试框架：pytest
- 覆盖场景：
  - [ ] 正常情况
  - [ ] 边界条件
  - [ ] 错误处理
  - [ ] [特定场景1]
  - [ ] [特定场景2]

### 测试数据
[提供测试数据或说明如何获取]

### 注意事项
- [需要 mock 的依赖]
- [需要特别关注的点]
```

---

## 4. 代码生成规范

### 4.1 文件头部

AI 生成的代码应包含标准文件头：

```python
"""
模块名称：[module_name]
描述：[简要描述模块功能]
作者：Ditto Team (AI Assisted)
创建日期：[日期]

依赖：
    - [dependency1]
    - [dependency2]

使用示例：
    >>> from ditto.engine import FactorEngine
    >>> engine = FactorEngine(data_service)
    >>> result = engine.calc_factors(trade_date, universe)
"""
```

### 4.2 类型注解

所有代码必须有完整的类型注解：

```python
# 好的示例
def calc_regime(
    self,
    trade_date: date,
    lookback_days: int = 60
) -> RegimeResult:
    """计算 Regime
    
    Args:
        trade_date: 交易日期
        lookback_days: 回看天数
        
    Returns:
        RegimeResult: 包含 regime_type 和 regime_score
        
    Raises:
        DataNotFoundError: 当数据不存在时
    """
    pass

# 不好的示例
def calc_regime(self, trade_date, lookback_days=60):
    pass
```

### 4.3 错误处理

```python
# 好的示例
try:
    data = self.data_service.get_kline(symbol, start_date, end_date)
except DataNotFoundError:
    logger.warning("data_not_found", symbol=symbol, start=start_date, end=end_date)
    return None
except DataSourceError as e:
    logger.error("data_source_error", symbol=symbol, error=str(e))
    raise

# 不好的示例
try:
    data = self.data_service.get_kline(symbol, start_date, end_date)
except Exception:
    pass  # 吞掉异常
```

### 4.4 日志规范

```python
# 好的示例：结构化日志
logger.info(
    "factor_calculation_complete",
    factor_name="rs_20d",
    symbols_count=50,
    duration_ms=1234
)

# 不好的示例：字符串拼接
logger.info(f"Factor rs_20d calculated for 50 symbols in 1234ms")
```

### 4.5 PIT 安全检查

```python
# 好的示例：明确使用 knowledge_date
def get_factors_pit(
    self,
    trade_date: date,
    as_of_date: date  # PIT: 数据可知日期
) -> pl.DataFrame:
    return self.db.query("""
        SELECT * FROM etf_factor_daily
        WHERE trade_date = ?
          AND knowledge_date <= ?  -- PIT 安全
    """, [trade_date, as_of_date])

# 不好的示例：没有 PIT 保护
def get_factors(self, trade_date: date) -> pl.DataFrame:
    return self.db.query("""
        SELECT * FROM etf_factor_daily
        WHERE trade_date = ?
    """, [trade_date])  # 可能使用了未来数据
```

---

## 5. 项目上下文提供

### 5.1 核心文档清单

与 AI 协作时，应根据任务提供相关文档：

| 文档 | 何时提供 | 包含内容 |
|------|----------|----------|
| 00_overview.md | 所有任务 | 项目背景、设计原则 |
| 01_system_design.md | 架构相关任务 | 系统分层、模块划分 |
| 02_data_design.md | 数据相关任务 | Schema、数据源 |
| 03_engine_design.md | 引擎相关任务 | 引擎接口、算法 |
| 09_risk_constitution.md | 风控相关任务 | 风控规则、阈值 |

### 5.2 上下文提供模板

```markdown
## 项目上下文

### 系统概述
Ditto 是一个个人量化交易系统，当前 Phase 0-1 聚焦 ETF 行业轮动策略。

### 技术栈
- Python 3.11+ / Polars / DuckDB / SQLite
- FastAPI / Next.js
- 单机 Windows 环境

### 核心设计原则
1. 不死优先：20% 回撤硬约束
2. 回测-实盘路径一致：对齐测试误差 < 0.1%
3. 数据为王：PIT 安全、复权分离存储
4. 本地闭环：不依赖云服务

### 当前任务相关的设计约束
[根据具体任务补充]
```

### 5.3 代码上下文提供

```markdown
## 相关代码

### 接口定义
```python
# 需要实现的接口
class Factor(ABC):
    @abstractmethod
    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        pass
```

### 依赖的类
```python
# 可用的数据服务
class DataService:
    def get_kline(self, symbol, start, end) -> pl.DataFrame: ...
    def get_factors_pit(self, symbols, trade_date, as_of_date) -> pl.DataFrame: ...
```

### 示例实现
```python
# 参考：RSFactor 的实现
class RSFactor(Factor):
    ...
```

---

## 6. Review 检查清单

### 6.1 AI 代码 Review 清单

- [ ] **功能正确性**：代码实现是否符合需求？
- [ ] **类型注解**：所有函数是否有完整类型注解？
- [ ] **错误处理**：是否正确处理异常？
- [ ] **日志记录**：关键操作是否有日志？
- [ ] **PIT 安全**：是否使用了 knowledge_date 约束？
- [ ] **涨跌停**：回测代码是否处理了涨跌停？
- [ ] **复权处理**：是否使用动态复权而非持久化复权价？
- [ ] **边界条件**：是否处理了空数据、单条数据等情况？
- [ ] **代码风格**：是否符合项目规范？
- [ ] **测试覆盖**：是否有对应的测试？

### 6.2 常见 AI 生成代码问题

| 问题类型 | 表现 | 修复方式 |
|----------|------|----------|
| 过度工程 | 不必要的抽象层 | 简化，YAGNI |
| 幻觉 API | 调用不存在的方法 | 检查实际 API |
| 忽略 PIT | 直接使用 trade_date 查询 | 添加 knowledge_date 约束 |
| 吞异常 | `except Exception: pass` | 明确异常处理 |
| 魔法数字 | 硬编码阈值 | 提取为配置或常量 |

---

## 7. 迭代开发流程

### 7.1 单个功能的开发流程

```
1. 人类：明确需求和设计
   ↓
2. 人类：编写 Prompt，提供上下文
   ↓
3. AI：生成初版代码
   ↓
4. 人类：Review，标注问题
   ↓
5. AI：根据反馈修改
   ↓
6. 人类：确认修改，本地测试
   ↓
7. AI：补充测试用例
   ↓
8. 人类：运行测试，集成
```

### 7.2 反馈迭代模板

```markdown
## 代码反馈

### 问题 1：[位置]
```python
# 当前代码
def calc_factor(...):
    ...
```
问题：[描述问题]
建议：[修改建议]

### 问题 2：[位置]
...

### 总体评价
[整体代码质量评价和优先修复项]

---

## 8. 知识沉淀

### 8.1 常见模式库

随着项目推进，沉淀常见代码模式供 AI 参考：

```markdown
# patterns/pit_safe_query.md

## PIT 安全查询模式

### 场景
获取历史某一天可知的因子数据

### 模式代码
```python
def get_factors_pit(
    self,
    trade_date: date,
    as_of_date: date
) -> pl.DataFrame:
    """PIT 安全的因子查询
    
    Args:
        trade_date: 交易日期
        as_of_date: 数据可知日期（通常等于 trade_date）
    """
    return self.db.query("""
        SELECT * FROM etf_factor_daily
        WHERE trade_date = ?
          AND knowledge_date <= ?
    """, [trade_date, as_of_date])
```

### 使用场景
- 回测时获取因子
- 历史 Regime 重建
- 任何需要避免 Look-Ahead Bias 的场景
```

### 8.2 错误案例库

记录 AI 生成代码中的典型错误：

```markdown
# mistakes/look_ahead_bias.md

## 错误：Look-Ahead Bias

### 错误代码
```python
def calc_value_factor(self, trade_date: date):
    # 错误：使用最新的财务数据，可能包含未来数据
    valuation = self.db.query("""
        SELECT * FROM etf_valuation WHERE trade_date = ?
    """, [trade_date])
```

### 正确代码
```python
def calc_value_factor(self, trade_date: date, as_of_date: date):
    # 正确：只使用当时可知的数据
    valuation = self.db.query("""
        SELECT * FROM etf_valuation 
        WHERE trade_date = ?
          AND report_date <= ?  -- 财报发布日
    """, [trade_date, as_of_date])
```

### 教训
财务数据（PE、PB）有发布时滞，回测时必须使用 PIT 约束
```

---

## 9. 安全与隐私

### 9.1 不应与 AI 共享的信息

- Tushare API Token
- 券商账号密码
- 个人投资金额
- 实盘交易记录
- 其他敏感配置

### 9.2 安全提示词

```markdown
注意：以下内容已脱敏处理

- API Token：ts_****1234
- 账户余额：[REDACTED]
- 配置路径：使用占位符 {CONFIG_PATH}
```

---

*本 AI 协作规范将随项目实践持续更新。目标是让人机协作更高效、代码质量更有保障。*
