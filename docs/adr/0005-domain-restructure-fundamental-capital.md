# ADR 0005: DataHub 域重构 - Fundamental 与 Capital 域拆分

**状态**: 已接受
**日期**: 2026-01-30
**决策者**: 架构团队
**相关 ADR**: [ADR 0004](0004-domain-layer-subdomains.md)

---

## 背景

在 DataHub v0.10.0 中，Capital 域混合了两种不同驱动变量的数据：

1. **企业基本面数据**：由公司公告驱动（财报、分红、业绩预告）
2. **资金与市场数据**：由交易行为驱动（融资融券、估值指标、期货）

这种混合导致以下问题：

| 问题 | 说明 | 影响 |
|------|------|------|
| **职责边界不清** | 企业基本面和资金面数据混在一起 | 违反单一职责原则 |
| **驱动变量不同** | 公告驱动 vs 交易驱动 | 数据摄入逻辑差异大 |
| **更新频率不同** | 季度/公告 vs 日频 | 存储和查询优化策略不同 |
| **用户认知混乱** | 用户不清楚数据分类 | API 使用体验差 |

---

## 决策

### 决策 1：拆分为 Fundamental 域和 Capital 域

**Fundamental 域（企业基本面）**

**职责**：存储和查询由公司公告驱动的企业基本面数据

**数据类型**：
- 财务报表：balance_sheet, income_statement, cash_flow
- 公司行为：dividend, corporate_actions
- 业绩预告/快报：forecast, express

**驱动变量**：公司公告（公告日期 = knowledge_date）

**目录结构**：
```
packages/data/src/ditto_data/domains/fundamental/
├── financial/           # 财务报表子域（计划中）
│   ├── balance_sheet_store.py
│   ├── income_statement_store.py
│   └── cash_flow_store.py
├── corporate/           # 公司行为子域（计划中）
│   ├── dividend_store.py
│   └── corporate_actions_store.py
├── forecast/            # 业绩预告子域
│   ├── forecast_store.py
│   └── express_store.py
├── fundamental_store.py # FundamentalStore（统一入口）
├── fundamental_service.py
└── fundamental_ingestion.py
```

**Capital 域（资金与市场）**

**职责**：存储和查询由交易行为驱动的资金与市场数据

**数据类型**：
- 融资融券：margin_trading
- 股权质押：pledge_ratio
- 估值指标：valuation_metrics
- 期货：futures
- 指数成分股：index_composition

**驱动变量**：交易日或市场行为（交易日 = trade_date）

**目录结构**：
```
packages/data/src/ditto_data/domains/capital/
├── margin/              # 融资融券子域
│   └── margin_trading_store.py
├── pledge/              # 股权质押子域
│   └── pledge_ratio_store.py
├── capital_store.py     # CapitalStore（统一入口）
├── capital_service.py
└── capital_ingestion.py
```

---

### 决策 2：Service 命名统一

**变更**：
- `MarketQueryService` → `MarketService`
- `MetadataQueryService` → `MetadataService`

**理由**：
- Service 本身就是查询服务，"Query" 是冗余词
- 与新增的 `FundamentalService`、`CapitalService` 保持命名一致
- 简洁性原则（YAGNI）

---

### 决策 3：子域 Store 命名规范

**规范**：子域 Store 使用 `_store.py` 后缀

**示例**：
- `margin_trading_store.py` → `MarginTradingStore`
- `pledge_ratio_store.py` → `PledgeRatioStore`
- `forecast_store.py` → `ForecastStore`

**导出规范**：子域 `__init__.py` 必须导出子域 Store

```python
"""Forecast 子域 - 业绩预告/快报数据。"""

from ditto_data.domains.fundamental.forecast.express_store import ExpressStore
from ditto_data.domains.fundamental.forecast.forecast_store import ForecastStore

__all__ = ["ExpressStore", "ForecastStore"]
```

---

## 决策理由

### 1. 单一职责原则（SRP）

**Fundamental 域**：企业基本面 = 公司公告驱动
- 财报：公司季度发布
- 分红：公司董事会决议
- 业绩预告：公司自愿披露

**Capital 域**：资金与市场 = 交易行为驱动
- 融资融券：每日交易数据
- 估值指标：每日市场数据
- 期货：每日交易数据

### 2. 驱动变量不同

| 域 | 驱动变量 | knowledge_date 来源 | 更新频率 |
|----|---------|-------------------|----------|
| Fundamental | 公司公告 | 公告日期 | 季度/不定期 |
| Capital | 交易行为 | 交易日次日 | 日频 |

### 3. 存储和查询优化策略不同

**Fundamental 域**：
- 强调 PIT 能力（数据修正场景）
- 索引优化：knowledge_date, report_date
- 查询模式：按报告期查询

**Capital 域**：
- 强调时序查询（时间序列分析）
- 索引优化：trade_date, instrument_id
- 查询模式：按时间范围查询

### 4. 用户认知一致性

**量化行业实践**：
- **Fundamental** = 企业基本面 = 财报、分红、业绩
- **Capital** = 资金面 = 融资融券、估值、期货

符合 WorldQuant、Two Sigma 等领先量化公司的数据分类方式。

---

## 影响分析

### 正面影响

1. ✅ **职责边界清晰**：Fundamental 和 Capital 各司其职
2. ✅ **驱动变量明确**：公告驱动 vs 交易驱动
3. ✅ **存储优化分离**：不同域可采用不同的存储策略
4. ✅ **用户认知一致**：符合量化行业实践
5. ✅ **可维护性提升**：代码组织更清晰
6. ✅ **可扩展性增强**：新数据类型可明确归属

### 需要调整的部分

1. **导入语句更新**：
   ```python
   # 旧
   from ditto_data.domains.capital import CapitalStore
   from ditto_data.domains.capital.capital_store import BalanceSheetStore

   # 新
   from ditto_data.domains.capital import CapitalStore
   from ditto_data.domains.fundamental import FundamentalStore
   ```

2. **Service 名称更新**：
   ```python
   # 旧
   from ditto_data.domains.market import MarketQueryService
   from ditto_data.domains.metadata import MetadataQueryService

   # 新
   from ditto_data.domains.market import MarketService
   from ditto_data.domains.metadata import MetadataService
   ```

3. **测试文件更新**：
   - `test_capital_service_unit.py` - 移除已迁移到 Fundamental 的数据类型测试
   - 新增 `test_fundamental_service_unit.py` - Fundamental 域单元测试

4. **文档更新**：
   - `packages/data/README.md` - 更新城架构说明
   - `docs/design/2026-01-26-datahub-complete-redesign.md` - 标记版本差异

---

## 实施计划

### Phase 1: 架构设计（已完成）

- ✅ 拆分 Fundamental 和 Capital 域
- ✅ 定义子域结构
- ✅ 确定 Service 命名规范

### Phase 2: 代码实现（已完成）

- ✅ 创建 Fundamental 域目录结构
- ✅ 创建 FundamentalStore 和 FundamentalService
- ✅ 创建 forecast 子域（ForecastStore、ExpressStore）
- ✅ 更新 CapitalStore（移除已迁移数据）
- ✅ 创建 Capital 域子域（margin、pledge）
- ✅ Service 重命名（MarketService、MetadataService）

### Phase 3: 测试覆盖（已完成）

- ✅ Fundamental 域单元测试
- ✅ Capital 域单元测试
- ✅ PIT 数据修正场景测试（新增）
- ✅ 集成测试更新

### Phase 4: 文档更新（已完成）

- ✅ README 更新
- ✅ 设计文档标记
- ✅ 创建 ADR

### Phase 5: 验证（进行中）

- ✅ 类型检查通过
- ✅ Lint 检查通过
- ⏳ 完整测试套件运行

---

## 相关文档

- [架构规范](../../.claude/rules/architecture.md)
- [DataHub README](../../packages/data/README.md)
- [域重构实施计划](../../plans/2026-01-30-domain-restructure-fundamental-capital.md)
- [ADR 0004: Domain Layer 子领域分层定位](0004-domain-layer-subdomains.md)

---

## 参考资料

### 业界实践

1. [WorldQuant Brain Data Taxonomy](https://www.worldquantbrain.com/data/) - 数据分类方式
2. [Two Sigma Data Engineering](https://www.twosigma.com/articles/our-approach-to-data-engineering) - 数据架构实践

### DDD 经典文献

- [Domain-Driven Design](https://www.domainlanguage.com/ddd/) - Eric Evans
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Uncle Bob

---

**文档版本**: 1.0
**最后更新**: 2026-01-30
