# 维度⑤：运维质量评估

> 基于 ISO 25010 可靠性/安全性/性能效率、ATAM 运行时质量属性、CNCF 可观测性最佳实践

---

## 评价项

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| O1 | **结构化日志** | ★★★ | loguru 结构化输出，关键操作有上下文，无敏感信息 | 日志审查 |
| O2 | **业务指标度量** | ★★★ | 核心指标可度量（回测耗时、管道延迟、策略 PnL） | 监控系统 |
| O3 | **分布式追踪** | ★★☆ | 关键链路有 OpenTelemetry 追踪 | 追踪系统 |
| O4 | **容错与重试** | ★★★ | 数据管道故障可自动重试（tenacity），有降级策略 | 代码审查 |
| O5 | **数据持久性** | ★★★ | 数据备份策略、WAL/事务保证数据不丢失 | 架构审查 |
| O6 | **性能基准** | ★★☆ | 关键路径有性能基线（回测吞吐、因子计算延迟） | Benchmark |
| O7 | **安全态势** | ★★★ | API 认证/授权、密钥管理、无已知漏洞依赖 | 安全扫描 |
| O8 | **配置管理** | ★★☆ | 环境隔离（dev/test/prod）、敏感信息不硬编码 | 配置审计 |
| O9 | **资源效率** | ★★☆ | 内存/CPU 使用合理，无资源泄漏 | 性能测试 |
| O10 | **灾备能力** | ★☆☆ | 可从灾难状态恢复（数据重建、状态恢复） | 灾备演练 |

## 量化阈值

| 指标 | 🟢 优秀 | 🟡 合格 | 🔴 需改进 |
|------|---------|---------|----------|
| 关键操作日志覆盖率 | 100% | ≥ 90% | < 90% |
| 数据管道故障恢复 | 自动重试 + 告警 | 自动重试 | 手动干预 |
| 已知漏洞 (Critical/High) | 0 | 0 (Critical) | > 0 (Critical) |
| 性能基准 | 有 + 自动化回归 | 有基准 | 无基准 |
| 环境隔离 | 严格分离 + 验证 | 分离但无验证 | 混用 |

## 检查命令

```bash
# 日志使用模式
grep -r "loguru\|from loguru import\|logger\." packages/ --include="*.py" | grep -v test | wc -l

# OpenTelemetry 追踪
grep -r "opentelemetry\|trace\|span" packages/ --include="*.py" | grep -v test | head -10

# 容错/重试模式
grep -r "tenacity\|retry\|@retry" packages/ --include="*.py" | grep -v test | head -10

# 密钥/敏感信息检查
grep -rE "password|secret|api_key|token.*=" packages/ --include="*.py" | \
  grep -v "test\|# \|config\|setting\|env\|os\.environ" | head -10

# 环境配置
ls config/*/ 2>/dev/null | head -20
cat .env* 2>/dev/null | head -10

# 依赖漏洞扫描（如果可用）
pip-audit 2>/dev/null || echo "pip-audit not installed"
```

## 评分规则

- O7（安全态势）为硬性项：有 Critical 漏洞 → 整个维度最高 2★
- O4（容错与重试）为关键项：fail → 扣 1★
- 其余项按 pass/warning/fail 正常计分
- 总分映射到 1-5 星
