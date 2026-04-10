# 命名与概念审查增强设计

## 概述

在 `ditto-architecture-audit.md` 中新增"命名与概念审查"独立章节，通过自动化检测与人工审查相结合的方式，识别代码库中的概念模糊、有歧义的命名问题。

## 设计目标

1. **自动化检测**：快速识别候选问题，提高审计效率
2. **人工审查**：结合业务上下文，准确判断问题严重性
3. **全面覆盖**：命名一致性、概念边界、抽象层次、缩写规范

## 实施方案

### 一、文档结构更新

在 `ditto-architecture-audit.md` 中，于"检查项清单"之后、"示例输出"之前，新增独立章节：

```markdown
## 命名与概念审查

### 自动化检测（混合方案）

#### 1. 规则模式匹配（快速检测）
- 命名风格一致性检查
- 缩写使用规范检查
- 术语一致性检查

#### 2. LSP 语义分析（深度检测）
- 概念边界分析（类/模块职责与命名匹配度）
- 抽象层次验证（技术术语 vs 业务术语）
- 依赖链中的命名追踪

### 人工审查指南

#### 四大审查维度
1. **命名一致性** - 同一概念的多术语问题
2. **概念边界** - 职责与命名不匹配
3. **抽象层次** - 业务概念与技术术语混用
4. **缩写规范** - 领域术语标准化

#### 审查流程
1. 执行自动化检测，收集候选问题
2. 人工复核每个候选问题
3. 根据业务上下文确认是否为真正问题
4. 生成改进建议和优先级排序
```

### 二、自动化检测实现

#### 规则模式匹配

在"传统模式匹配（补充）"章节中增加：

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

# 缩写使用规范检查
# 检测非标准缩写和领域术语不一致
grep -rE "\b(qty|vol|ohlcv|ticker)\b" packages/ apps/ --include="*.py" | \
  grep -v "qty.*=.*quantity\|#.*qty\|\"qty\"\|'qty'"

# 业务术语与技术术语混用检测
# 检测类名中同时包含业务和技术术语的模式
grep -rE "class.*Database.*Manager|class.*SQL.*Service" packages/ apps/ --include="*.py"
```

#### LSP 语义分析

在"LSP 语义分析（优先）"章节中增加：

```markdown
**命名与概念检查**：
- 使用 `documentSymbol` 获取类/函数的符号列表，提取命名
- 使用 `findReferences` 追踪命名使用情况，检测孤立命名
- 使用 `hover` 获取类型信息，分析命名与类型的语义匹配度
- 对比类名与其方法/属性命名，检测职责一致性
```

### 三、人工审查指南

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

### 四、Python 实现扩展

在 `architecture-audit.py` 中新增分析器类：

```python
class NamingConceptAnalyzer:
    """命名与概念分析器"""

    def analyze_naming_consistency(self, symbols: list[DocumentSymbol]) -> list[Finding]:
        """分析命名一致性"""
        findings = []
        # 提取所有命名，建立术语映射
        # 检测同义词、风格混用、缩写不一致
        return findings

    def analyze_concept_boundaries(self, classes: list[ClassSymbol]) -> list[Finding]:
        """分析概念边界（职责与命名匹配度）"""
        findings = []
        for cls in classes:
            # 检查类名与方法/属性的语义一致性
            # 检测职责过重但命名未体现的情况
        return findings

    def analyze_abstraction_levels(self, modules: list[Module]) -> list[Finding]:
        """分析抽象层次（业务术语 vs 技术术语）"""
        findings = []
        for module in modules:
            # 检查 Port 层是否混用技术术语
            # 检查领域层是否包含框架概念
        return findings

    def analyze_abbreviations(self, symbols: list[DocumentSymbol]) -> list[Finding]:
        """分析缩写规范"""
        findings = []
        # 检测非标准缩写
        # 检测同一缩写多种形式
        return findings

# 在主审计流程中集成
def run_architecture_audit():
    # ... 现有检查 ...

    # 新增：命名与概念审查
    naming_analyzer = NamingConceptAnalyzer()
    naming_findings = naming_analyzer.analyze_all()

    # 合并到总报告
    all_findings.extend(naming_findings)
```

### 五、报告输出格式

在审计报告中新增"命名与概念"问题分类：

```markdown
## Findings

### 架构约束
- [ARCH-001] BarsRepository 职责过重 (1081行)

### 命名与概念
- [NAM-001] `BarData` / `KlineData` / `CandlestickData` 概念不统一
  - 位置: `packages/data/src/ditto_data/models/`
  - 严重度: P1
  - 建议: 统一使用 `BarData`

- [NAM-002] Port 层混用技术术语 `SQLBarLoader`
  - 位置: `apps/port/src/ditto_port/services/sql_bar_loader.py`
  - 严重度: P0
  - 建议: 重命名为 `BarDataLoader`，技术细节由 DataHub 处理

### 工程实践
- [ENG-001] ...
```

### 六、检查项清单更新

在"检查项清单"中新增分类：

```markdown
### 命名与概念
- [ ] 同一概念多种表述（bar / kline / candlestick）
- [ ] 命名风格混用（驼峰 / 下划线 / 全大写）
- [ ] 缩写不一致（qty / quantity / quant）
- [ ] 类命名与职责不匹配
- [ ] 业务层使用技术术语（SQL / Parquet）
- [ ] 领域层包含框架概念（Request / Response）
- [ ] 跨层技术术语泄漏
- [ ] 非标准缩写使用
```

### 七、示例输出更新

```markdown
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

## 预期收益

1. **可读性提升**：统一命名风格，降低理解成本
2. **可维护性增强**：清晰的职责边界，便于重构和扩展
3. **领域建模清晰**：业务与技术分离，符合 DDD 原则
4. **新人友好**：一致的术语体系，加速团队协作

## 实施计划

| 阶段 | 任务 | 产出 |
|------|------|------|
| P0 | 更新 `ditto-architecture-audit.md` 文档 | 完整的审查指南 |
| P1 | 实现规则模式匹配检测 | 快速检测脚本 |
| P2 | 实现 LSP 语义分析 | 深度分析能力 |
| P3 | 集成到现有审计流程 | 统一的审计报告 |

## 相关文档

- [ditto-architecture-audit.md](.claude/commands/ditto-architecture-audit.md)
- [architecture-audit.py](.claude/commands/architecture-audit.py)
- [architecture.md](.claude/rules/architecture.md)
- [core.md](.claude/rules/core.md)
