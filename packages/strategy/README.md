# ditto-strategy

策略定义与信号生成能力包。

## 功能

- **Alpha Pipeline**: 可组合的 Stage 模式策略管线（DecisionStage Protocol）
- **策略模板**: ETF轮动、趋势摆动、多因子选股、行业轮动
- **信号契约**: SignalStore Protocol 定义信号持久化接口
- **策略规格**: StrategySpec 冻结数据类 + 参数验证

## 安装

```bash
pixi install -e dev
```

## 测试

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q
```
