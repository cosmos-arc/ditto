# 宏观数据源实施计划

**日期**: 2026-02-25
**状态**: 待实施
**设计文档**: [宏观数据源统一设计](2026-02-25-macro-data-source-design.md)

---

## 概述

### 目标范围

**仅处理纯宏观数据**（不包括 Market 相关的利率、汇率、商品等）

| 地区 | 数据源 | 指标 | 频率 |
|------|--------|------|------|
| 中国 | Tushare | GDP、CPI、PPI、PMI、M2、社融 | 季度/月度 |
| 美国 | FRED | GDP、CPI、PCE、失业率、M2 | 季度/月度 |

### 完整指标列表

**中国宏观指标（Tushare）**

| 指标代码 | 指标名称 | API | 频率 | 发布规律 |
|---------|---------|-----|------|---------|
| CN_GDP_YOY | 中国GDP同比 | cn_gdp | 季度 | 季后15日 |
| CN_CPI_YOY | 中国CPI同比 | cn_cpi | 月度 | 次月9日 |
| CN_PPI_YOY | 中国PPI同比 | cn_ppi | 月度 | 次月9日 |
| CN_PMI_MFG | 中国制造业PMI | cn_pmi | 月度 | 次月1日 |
| CN_M2_YOY | 中国M2同比 | cn_m | 月度 | 次月13日 |
| CN_M1_YOY | 中国M1同比 | cn_m | 月度 | 次月13日 |
| CN_M0_YOY | 中国M0同比 | cn_m | 月度 | 次月13日 |
| CN_CREDIT_TS | 中国社会融资规模 | cn_shz | 月度 | 次月13日 |

**美国宏观指标（FRED）**

| 指标代码 | 指标名称 | Series ID | 频率 |
|---------|---------|-----------|------|
| US_GDP_QOQ | 美国GDP环比 | A191RL1Q225SBEA | 季度 |
| US_CPI_YOY | 美国CPI同比 | CPIAUCSL | 月度 |
| US_CPI_CORE_YOY | 美国核心CPI同比 | CPILFESL | 月度 |
| US_PCE_YOY | 美国PCE同比 | PCEPI | 月度 |
| US_PCE_CORE_YOY | 美国核心PCE同比 | PCEPILFE | 月度 |
| US_UNRATE | 美国失业率 | UNRATE | 月度 |
| US_PAYEMS | 美国非农就业 | PAYEMS | 月度 |
| US_M2_YOY | 美国M2同比 | M2SL | 月度 |

---

## 技术方案

### 存储复用

复用现有 `MACRO_INDICATOR_SOURCE_SCHEMA`，无需修改存储层：

```python
MACRO_INDICATOR_SOURCE_SCHEMA = SourceSchema(
    dataset="macro_indicators",
    key_columns=("indicator_code", "date", "knowledge_date"),
    schema={
        "indicator_code": pl.String,
        "indicator_name": pl.String,
        "category": pl.String,
        "frequency": pl.String,
        "need_pit": pl.Boolean,
        "date": pl.Date,
        "value": pl.Float64,
        "knowledge_date": pl.Date,
        "source": pl.String,
        "unit": pl.String,
        "description": pl.String,
    },
)
```

### knowledge_date 估算策略

**Tushare（中国）**：基于官方发布规律估算

| 指标类型 | 发布规律 |
|---------|---------|
| GDP（季度） | 季后15日（Q4为次年1月17日） |
| CPI/PPI | 次月9日 |
| PMI | 次月1日 |
| M0/M1/M2 | 次月13日 |
| 社会融资规模 | 次月13日 |

**FRED（美国）**：使用 API 提供的 `realtime_start` 字段

### 新增目录结构

```
packages/datahub/src/ditto_datahub/sources/
├── fred/                           # 新增 FRED 数据源
│   ├── __init__.py
│   ├── client.py                   # FredClient: HTTP 请求封装
│   ├── fred_source.py              # FredSource: DataSource 实现
│   └── indicators.py               # FRED 指标元数据定义
├── tushare/
│   ├── adapters/
│   │   └── macro.py                # 扩展现有实现
│   └── indicators/                 # 新增
│       ├── __init__.py
│       ├── tushare_indicators.py   # Tushare 宏观指标定义
│       └── knowledge_date.py       # knowledge_date 估算逻辑
└── schemas/
    └── macro_schemas.py            # 复用现有
```

---

## 任务清单

### Phase 1：基础设施 - FRED 客户端 `[L]`

- [ ] **Task 1.1**: 创建 FRED 数据源目录结构 `[S]`
  - 验收: 目录 `packages/datahub/src/ditto_datahub/sources/fred/` 创建完成
  - 文件: `fred/__init__.py`

- [ ] **Task 1.2**: 实现 FredClient `[M]`
  - 验收:
    - HTTP 请求封装，支持 tenacity 重试
    - 支持 PIT 查询参数（realtime_start/realtime_end）
    - 返回 polars DataFrame
    - 单元测试覆盖
  - 文件: `fred/client.py`, `tests/unit/sources/fred/test_client_unit.py`

- [ ] **Task 1.3**: 实现 FRED 指标元数据 `[S]`
  - 验收:
    - FredIndicator dataclass 定义
    - 完整指标注册表（US_GDP_QOQ, US_CPI_YOY, US_CPI_CORE_YOY, US_PCE_YOY, US_PCE_CORE_YOY, US_UNRATE, US_PAYEMS, US_M2_YOY）
  - 文件: `fred/indicators.py`

- [ ] **Task 1.4**: 实现 MacroFredAdapter `[M]`
  - 验收:
    - 继承/复用现有 Adapter 模式
    - 数据标准化为 MACRO_INDICATOR_SOURCE_SCHEMA
    - knowledge_date 从 realtime_start 获取
    - 单元测试覆盖
  - 文件: `fred/adapters/macro.py`, `tests/unit/sources/fred/test_macro_adapter_unit.py`

### Phase 2：Tushare 扩展 - 中国宏观数据 `[L]`

- [ ] **Task 2.1**: 实现 knowledge_date 估算逻辑 `[M]`
  - 验收:
    - estimate_knowledge_date() 函数
    - determine_knowledge_date() 函数（含优化策略）
    - GDP/CPI/PPI/PMI/M2 发布规律映射
    - 单元测试覆盖（含边界条件）
  - 文件: `tushare/indicators/knowledge_date.py`, `tests/unit/sources/tushare/test_knowledge_date_unit.py`

- [ ] **Task 2.2**: 实现 Tushare 宏观指标元数据 `[S]`
  - 验收:
    - TushareMacroIndicator dataclass 定义
    - 完整指标注册表（CN_GDP_YOY, CN_CPI_YOY, CN_PPI_YOY, CN_PMI_MFG, CN_M2_YOY, CN_M1_YOY, CN_M0_YOY, CN_CREDIT_TS）
    - 日期解析工具（季度/月度格式）
  - 文件: `tushare/indicators/tushare_indicators.py`

- [ ] **Task 2.3**: 重构 MacroTushareAdapter `[M]`
  - 验收:
    - 使用新的指标元数据系统
    - 支持 fetch_indicators(codes, start_date, end_date) 接口
    - 集成 knowledge_date 估算逻辑
    - 日期范围摄取模式
    - 单元测试覆盖
  - 文件: `tushare/adapters/macro.py`, `tests/unit/sources/tushare/test_macro_adapter_unit.py`

### Phase 3：CLI 集成 `[M]`

- [ ] **Task 3.1**: 扩展宏观摄取 CLI `[M]`
  - 验收:
    - `pixi run ingest macro cn --start DATE --end DATE`
    - `pixi run ingest macro fred --start DATE --end DATE`
    - `pixi run ingest macro --indicators CODE1,CODE2`
    - 支持 --force 强制重摄取
  - 文件: `apps/port/src/ditto_port/cli/commands/ingest/macro.py`

### Phase 4：配置与文档 `[S]`

- [ ] **Task 4.1**: 添加 FRED API Key 配置 `[S]`
  - 验收:
    - config/development/data_source.env 添加 FRED_API_KEY
    - DataSourceSettings 支持 fred_api_key 字段
  - 文件: `config/development/data_source.env`, `ditto_datahub/config.py`

- [ ] **Task 4.2**: 集成测试 `[M]`
  - 验收:
    - FRED 端到端摄取测试（mock）
    - Tushare 端到端摄取测试（mock）
  - 文件: `tests/integration/sources/fred/`, `tests/integration/sources/tushare/`

---

## 依赖关系

```
Phase 1 (FRED) ─────┐
                    ├──► Phase 3 (CLI) ──► Phase 4 (配置/测试)
Phase 2 (Tushare) ──┘
```

Phase 1 和 Phase 2 可并行执行。

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Tushare API 积分限制 | 无法获取部分指标 | 使用已有积分账户，分批实施 |
| FRED API 限流 | 摄取速度受限 | tenacity 重试 + 合理限流配置 |
| 节假日发布日期估算偏差 | knowledge_date 不精确 | 后续可维护发布日历表 |

---

## 验收标准

1. **功能验收**
   - [ ] FRED 全部 8 个指标可摄取并存储
   - [ ] Tushare 全部 8 个指标可摄取并存储
   - [ ] knowledge_date 估算符合设计文档

2. **质量验收**
   - [ ] 单元测试覆盖率 ≥ 80%
   - [ ] 类型检查通过 (pyright strict)
   - [ ] Lint 检查通过 (ruff)

3. **文档验收**
   - [ ] 设计文档更新完整
   - [ ] 代码注释清晰
