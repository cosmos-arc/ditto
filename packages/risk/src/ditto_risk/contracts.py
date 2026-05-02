"""
Risk contracts — 跨模块共享的 Protocol 定义。

定义 RiskConstraint、RiskReport 等 Protocol，供 application 层
和其它能力包依赖。所有风控对外暴露的能力接口应在此注册，
包括约束检查器、风险评估器等可注入的抽象。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
