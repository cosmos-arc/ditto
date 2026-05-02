"""
Strategy contracts — 跨模块共享的 Protocol 定义。

供 strategy 消费者（application、backtest 等）依赖的公共契约接口，
包括 SignalProvider、StrategyRunner 等 Protocol。
扩展时应在此注册所有 strategy 对外暴露的能力接口。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""
