# 数据集晋级治理(历史注记)

> 晋级/认证/许可治理工作流已于 [#392](https://github.com/cosmos-arc/ditto/issues/392)
> 删除,`ditto ops promotion-collect/review/history/revoke` 命令不再存在。
> 决策背景与最终形态见 [数据层精简审阅](../../../docs/data/data-layer-review-2026-10.md)
> 与 [数据层全景图](../../../docs/data/data-layer-map.md)。
>
> 仍有效的精确快照读取命令为 `ditto data-products read-snapshot <snapshot-id>`
> 与 `ditto data-products replay-snapshots request.json`(请求需明确快照、证券、
> 字段、业务区间、knowledge/publication cutoff 和用途;资格不足或不完整返回失败,
> 不回退最新分区)。
