---
name: ditto-architecture-audit
description: "全库架构审计 - 检查分层、依赖、工程质量、测试覆盖（LSP优先）"
implementation: .claude/commands/architecture-audit.py
---

运行全库架构审计，生成完整的审计报告。

## 审计范围

- `packages/` - kernel、data、infra、engine、analytics、app
- `interfaces/` - API/CLI/Jobs + DI Composition Root
- `tests/` - 单元测试、集成测试、fixtures

## 执行步骤

### 1. 运行代码质量检查

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --unit
pixi run -e dev test --integration
```

### 2. 加载规则和配置

- 读取 `.claude/CLAUDE.md` - 项目核心约束
- 读取 `.claude/rules/*.md` - 具体规范
- 读取 `pyproject.toml` - basedpyright、ruff、pytest 配置
- 读取 `.pre-commit-config.yaml` - 钩子规则
- 读取 `.github/workflows/*.yml` - CI 检查项

### 3. LSP 语义分析（优先）

> 使用 `.claude/scripts/lsp_pyright.py` 进行 LSP 分析

**架构约束检查**：
- 使用 `refs` 检测死代码和未引用导出
  ```bash
  pixi run -e dev python .claude/scripts/lsp_pyright.py refs <file> <line> <col>
  ```
- 使用 `goto` 追踪依赖链，检测循环依赖
  ```bash
  pixi run -e dev python .claude/scripts/lsp_pyright.py goto <file> <line> <col>
  ```
- 使用 `symbols` 分析类/函数规模和结构
  ```bash
  pixi run -e dev python .claude/scripts/lsp_pyright.py symbols <file>
  ```
- 从 app 层出发，检查是否存在**真正的层级穿透**：

**层级穿透定义**（注意：Foundation 是横切层，可跨层访问）：
- ❌ interfaces → data storage/runtime（应通过 Service）
- ❌ engine → data（beyond errors/provider）
- ❌ engine → infra
- ✅ interfaces → data services/sources（允许）
- ✅ interfaces → infra foundation（允许，横切层）
- ✅ app → data → infra（正常依赖链）

**工程实践检查**：
- 使用 `symbols` 识别类规模（>300行）、方法数量（>15个）
- 使用 `hover` 获取类型信息，检测 Any 类型滥用
  ```bash
  pixi run -e dev python .claude/scripts/lsp_pyright.py hover <file> <line> <col>
  ```
- 使用 `diagnose` 收集实时错误和警告
  ```bash
  pixi run -e dev python .claude/scripts/lsp_pyright.py diagnose <file>
  ```

**命名与概念检查**：
- 使用 `symbols` 获取类/函数的符号列表，提取命名
- 使用 `refs` 追踪命名使用情况，检测孤立命名
- 使用 `hover` 获取类型信息，分析命名与类型的语义匹配度
- 对比类名与其方法/属性命名，检测职责一致性
- 分析 Port 层命名是否混用技术术语（如 `SQLBarLoader`）
- 检测同一概念的不同表述（如 `Bar`/`Kline`/`Candlestick`）

### 4. 传统模式匹配（补充）

```bash
# 命名风格一致性检查
# 检测同一实体的不同命名风格（如 user_id vs userId vs UserID）
pixi run -e dev python -c "
import ast
import re
from pathlib import Path

# 提取所有变量/函数/类名，建立命名变体映射
# 例如: {'user': ['user_id', 'userId', 'UserID', 'user']}
"

# 搜索 TYPE_CHECKING 使用
grep -r "TYPE_CHECKING" packages/ apps/ --include="*.py"

# 搜索空 TYPE_CHECKING 块
grep -r "if TYPE_CHECKING:\s*pass" packages/ apps/ --include="*.py"

# 搜索禁止的导入
grep -r "import pandas\|import sqlalchemy" packages/ apps/ --include="*.py"

# 搜索 type:ignore 使用
grep -r "# type: ignore" packages/ apps/ --include="*.py" | wc -l

# 缩写使用规范检查
# 检测非标准缩写和领域术语不一致
grep -rE "\b(qty|vol|ohlcv|ticker)\b" packages/ apps/ --include="*.py" | \
  grep -v "qty.*=.*quantity\|#.*qty\|\"qty\"\|'qty'"

# 业务术语与技术术语混用检测
# 检测类名中同时包含业务和技术术语的模式
grep -rE "class.*Database.*Manager|class.*SQL.*Service|class.*Parquet.*Writer" packages/ apps/ --include="*.py"
```

### 5. 生成架构图

```python
# 基于导入关系构建依赖图
for module in modules:
    for imp in get_imports(module):
        dependency_graph.add_edge(module, imp)

# 检测循环依赖
cycles = find_cycles(dependency_graph)

# 生成 ASCII 架构图
architecture_diagram = render_ascii(dependency_graph)
```

### 6. 生成报告

输出到 `docs/reviews/YYYY-MM-DD-architecture-audit.md`

**报告结构**：
- Executive Summary（关键统计、Top 3 问题）
- Inferred Architecture（架构图、依赖方向）
- Findings（详细发现，带证据和修复建议）
- Refactor Plan（按 P0/P1/P2 分组）

## 输出

1. **控制台输出**：摘要信息
   - 发现的问题数量（按严重度分类）
   - Top 5 高优先级问题
   - 报告文件路径

2. **Markdown 报告**：完整审计报告
   - 位置：`docs/reviews/YYYY-MM-DD-architecture-audit.md`
   - 包含：架构图、详细发现、修复计划、验证命令

## 检查项清单

### 架构约束
- [ ] 层级穿透检查
- [ ] 循环依赖检查
- [ ] 领域层污染检查
- [ ] 模块边界泄露检查
- [ ] 反向依赖检查

### 设计与结构
- [ ] 类单一职责（SRP）
- [ ] 类规模检查（>300行）
- [ ] 函数复杂度检查
- [ ] 模块划分合理性
- [ ] 包命名规范

### 依赖合规性
- [ ] 禁止的类库（pandas、sqlalchemy）
- [ ] 允许的类库（polars、duckdb、fastapi、prefect、loguru、orjson、granian、httpx）
- [ ] 包管理合规（pixi only）

### 工程实践
- [ ] TYPE_CHECKING 空块
- [ ] TYPE_CHECKING 过度使用
- [ ] 未使用的 Protocol
- [ ] 重复代码/方法
- [ ] 死代码（未引用）
- [ ] 异常处理缺失上下文
- [ ] 资源管理问题
- [ ] type:ignore 滥用
- [ ] Any 类型滥用

### 测试质量
- [ ] 测试可运行性
- [ ] 测试成功率
- [ ] 分支覆盖率 >= 80%
- [ ] 测试可维护性（fixture、断言、耦合）

### 命名与概念
- [ ] 同一概念多种表述（bar / kline / candlestick）
- [ ] 命名风格混用（驼峰 / 下划线 / 全大写）
- [ ] 缩写不一致（qty / quantity / quant）
- [ ] 类命名与职责不匹配
- [ ] 业务层使用技术术语（SQL / Parquet）
- [ ] 领域层包含框架概念（Request / Response）
- [ ] 跨层技术术语泄漏
- [ ] 非标准缩写使用

## 命名与概念审查

### 自动化检测

通过规则模式匹配和 LSP 语义分析相结合，快速识别候选问题。

#### 规则模式匹配（快速检测）
- **命名风格一致性检查**：检测驼峰、下划线、全大写风格混用
- **缩写使用规范检查**：检测非标准缩写和领域术语不一致
- **术语一致性检查**：检测业务术语与技术术语混用

#### LSP 语义分析（深度检测）
- **概念边界分析**：对比类/模块职责与命名的匹配度
- **抽象层次验证**：分析业务术语与技术术语的混用情况
- **依赖链命名追踪**：检测命名在依赖链中的语义一致性

### 人工审查指南

#### 1. 命名一致性审查

**审查原则**：同一概念在代码库中应使用统一的术语和命名风格。

**检查清单**：
- [ ] 同一业务概念的多种表述（如 `bar` / `kline` / `candlestick`）
- [ ] 驼峰与下划线风格混用（如 `userId` / `user_id` / `User_ID`）
- [ ] 单复数不一致（如 `BarRepository` / `bars_repository` / `bar_repo`）
- [ ] 缩写与全称混用（如 `qty` / `quantity` / `quant`）

**典型问题示例**：
```python
# ❌ 不一致：同一概念多种表述
class BarData: ...
class KlineStore: ...  # 应为 BarStore
class CandlestickRepository: ...  # 应为 BarRepository

# ❌ 不一致：风格混用
class bar_processor: ...  # 应为 BarProcessor
def fetchUserData(): ...  # 应为 fetch_user_data
```

**修复建议**：建立领域术语表，统一命名风格。

---

#### 2. 概念边界审查

**审查原则**：类/模块的命名应准确反映其职责，避免误导性命名。

**检查清单**：
- [ ] 类名包含多个职责（如 `DataManager` 同时做存储和计算）
- [ ] 命名过于宽泛（如 `Processor` / `Handler` / `Helper`）
- [ ] 抽象与实现混淆（如接口命名含 `Impl` 后缀）

**典型问题示例**：
```python
# ❌ 职责过重但命名未体现
class DataService:  # 实际包含：验证、转换、存储、计算
    def validate(self): ...
    def transform(self): ...
    def save(self): ...
    def calculate(self): ...

# ✅ 拆分为明确的职责类
class DataValidator: ...
class DataTransformer: ...
class DataRepository: ...
class DataCalculator: ...
```

**修复建议**：根据单一职责原则拆分或重命名。

---

#### 3. 抽象层次审查

**审查原则**：业务层代码应使用业务术语，技术层代码才使用技术术语。

**检查清单**：
- [ ] 业务层出现技术术语（如 `SQLManager` / `DatabaseProcessor`）
- [ ] 领域层包含框架概念（如 `RequestHandler` / `ResponseBuilder`）
- [ ] 跨层概念泄漏（如 Port 层直接使用 `SQLite` / `Parquet`）

**典型问题示例**：
```python
# ❌ 业务层混用技术术语
class SQLBarLoader: ...  # Port 层不应知道 SQL
class ParquetDataWriter: ...  # 应为 BarDataWriter

# ✅ 使用业务术语
class BarDataLoader: ...  # 内部实现由 DataHub 层处理
class BarDataWriter: ...
```

**修复建议**：遵循分层架构，每层使用对应层次的术语。

---

#### 4. 缩写规范审查

**审查原则**：缩写应在项目内保持一致，优先使用全称或行业标准缩写。

**检查清单**：
- [ ] 非标准缩写（如 `qty` 应为 `quantity`）
- [ ] 同一缩写多种形式（如 `vol` / `volume` / `volm`）
- [ ] 金融领域术语标准化（如 `OHLCV` / `ticker` / `bar`）

**典型问题示例**：
```python
# ❌ 缩写不一致
order_qty = 100  # 应为 order_quantity
volume_vol = 1000  # 冗余，应为 volume

# ✅ 统一缩写规范
order_quantity = 100
volume = 1000  # 标准金融术语
```

**修复建议**：建立缩写词典，强制统一使用。

### 审查流程

1. **执行自动化检测**：收集候选问题
2. **人工复核**：根据业务上下文确认是否为真正问题
3. **生成改进建议**：按 P0/P1/P2 分级
4. **输出到报告**：在 Findings 中新增 `[NAM-XXX]` 标识

## 示例输出

```
🔍 Architecture Audit Report

📊 Summary:
  Blocker: 0 | High: 5 | Medium: 12 | Low: 8

🔴 Top 5 Issues:
  1. [ARCH-001] BarsRepository 职责过重 (1081行)
  2. [NAM-001] Port层混用技术术语 `SQLBarLoader`
  3. [ARCH-004] DQ Checkers hub: Any 类型污染
  4. [NAM-003] `BarData`/`KlineData`/`CandlestickData` 概念不统一
  5. [ENG-002] 5处异常处理缺失上下文

📄 Full report: docs/reviews/2026-01-17-architecture-audit.md
```
