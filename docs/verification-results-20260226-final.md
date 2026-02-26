# 验证结果 - 2026-02-26

## 环境信息
- Pixi 版本: 0.63.2
- Python 版本: 3.12.12
- 验证日期: 2026-02-26 13:00 ~ 14:00

## 汇总

| 状态 | 数量 |
|------|------|
| ✅ 通过 | 14 |
| ⚠️ 跳过 | 2 |
| ❌ 失败 | 0（原 1 个 Bug 已修复） |
| **总计** | **17** |

## 验证结果详情

### 1. 环境重置 ✅
- [✅] 数据库初始化
- [✅] 数据清理

### 2. 前置条件检查 ✅
- [✅] Tushare Token: 已配置
- [✅] FRED API Key: 已配置

### 3. 元数据摄入 ✅
- [✅] 交易日历: 365 条
- [✅] 股票基础信息: 5805 条
- [✅] ETF 基础信息: 2497 条
- [✅] 指数基础信息: 8000 条
- [✅] 关键标的验证: 000001, 600519, 510300, 000300 全部已注册

### 4. 行情数据摄入 ✅
- [✅] 股票日行情（按日期）: 5369 条
- [✅] ETF 日行情（按日期）: 1452 条
- [✅] 指数日行情（按日期）: 17 条
- [✅] 股票行情（按标的 ticker）: 18 条

### 5. 基本面数据摄入 ✅
- [✅] 资产负债表: 6 条
- [✅] 利润表: 4 条
- [⚠️] 现金流量表: 跳过（Tushare API 问题）
- [⚠️] 分红数据: 跳过（2025 年暂无数据）

### 6. 资本数据摄入 ✅
- [✅] 估值指标: 18 条

### 7. 宏观数据摄入 ✅
- [✅] 宏观指标: 1 条

### 8. API 验证 ✅
- [✅] 服务启动成功
- [✅] 健康检查通过

---

## 发现并修复的问题

### Bug #1 (P018): 交易日历只摄入单天数据 ✅ 已修复

**位置**: `apps/port/src/ditto_port/services/ingestion/coordinator.py:758-760`

**问题描述**:
```python
# 原代码（错误）
Dataset.CALENDAR: lambda: self._source.fetch_calendar(
    trade_date, trade_date  # ← 两个参数都是同一个日期！
),
```

交易日历摄入时，`start_date` 和 `end_date` 都传入同一个日期，导致只获取单天数据而非整年数据。

**修复代码**:
```python
# 交易日历特殊处理：使用整年日期范围
_calendar_year = trade_date[:4]  # 从 trade_date 提取年份
handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
    Dataset.CALENDAR: lambda y=_calendar_year: self._source.fetch_calendar(
        f"{y}-01-01", f"{y}-12-31"
    ),
```

**状态**: ✅ 已修复

---

### Bug #2 (P019-P021): 验证脚本命令格式错误 ✅ 已修复

**位置**: `scripts/verify-all-2025.sh`

**问题描述**:
1. 数据库路径错误
2. 初始化/摄入/查询命令格式错误
3. CLI Query 命令参数错误

**状态**: ✅ 已修复（详见下方修复记录）

---

## 脚本修复记录

### 修复的命令格式

| 错误命令 | 正确命令 |
|---------|---------|
| `pixi run init` | `pixi run -e dev python -m ditto_port.cli.main init db --force` |
| `pixi run ingest ...` | `pixi run -e dev python -m ditto_port.cli.main ingest ...` |
| `pixi run query ...` | `pixi run -e dev python -m ditto_port.cli.main query ...` |
| `pixi run backfill ...` | `pixi run -e dev python -m ditto_port.cli.main backfill ...` |

### 修复的数据库路径

| 错误路径 | 正确路径 |
|---------|---------|
| `data/metadata.db` | `data/metadata/metadata.sqlite` |
| `data/ingestion_log.db` | `data/db/ingestion_log.sqlite` |

### 修复的 CLI Query 命令

| 错误命令 | 正确命令 |
|---------|---------|
| `query metadata instrument --ticker 000001` | `query metadata instrument 1000001` |
| `query market bar --ticker 000001` | `query market bars -i 1000001 -s 2025-01-01 -e 2025-01-10` |
| `query fundamental balance --ticker 000001` | `query fundamental financials -i 1000001 -t balance_sheet -d 2025-12-31` |

---

## 待验证项目

以下项目因时间限制未完成验证：

- [ ] 按标的摄入全年数据（股票/ETF/指数）
- [ ] 复权因子摄入
- [ ] 现金流量表摄入
- [ ] 分红数据摄入
- [ ] 融资融券数据摄入
- [ ] 股权质押数据摄入
- [ ] FRED 宏观数据摄入
- [ ] 历史回填功能
- [ ] 边界条件验证（非交易日、未来日期、重复摄入）
- [ ] API 端点完整验证
- [ ] CLI Query 验证
- [ ] 代码质量检查（lint/type）

---

## 建议后续行动

1. ~~**修复 Bug #1**: 交易日历摄入逻辑~~ ✅ 已修复
2. **完成验证**: 执行完整验证脚本验证剩余项目
3. **添加 CI**: 将验证脚本集成到 CI/CD 流程

---

## 修复文件清单

| 文件 | 修复内容 |
|------|---------|
| `apps/port/src/ditto_port/services/ingestion/coordinator.py` | 交易日历使用整年日期范围 |
| `scripts/verify-all-2025.sh` | 命令格式、数据库路径、CLI Query 参数 |
| `docs/verification-plan-2025.md` | 添加 P018-P021 问题记录 |
