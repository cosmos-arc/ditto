# 因子物化阶段二详设(#398)

> 状态:设计完成,待实施。阶段一(#391-#397)已交付最终数据层地基:
> 完成快照事实(checkpoint.complete_evidence_id)、观察事件表、数据集级
> catalog、快照就绪检查。本文档是 #390 D10 的落地设计。

## 1. 首个消费者与断点

研究/IC 评估链**已完整存在**:`FactorEvaluator`(IC/quantile/Fama-MacBeth/
per-date series)经 `FactorEvaluationFacade` 消费 `DerivedArtifactReader`
读物化产物。断点不在评估器,在**物化生产端**:derived 写侧从未产出真实
artifact(评审时 14 表 0 行),评估链因此只在夹具上跑通过。

首个实施切片 = 打通"**因子计算 → derived artifact 保存 → 研究/IC 读取**"
最小链,不重建控制面。

## 2. 产物身份(复用现有 manifest 能力)

每个物化产物绑定(全部已有承载,不新建泛化 feature store):

| 身份维度 | 承载 |
| --- | --- |
| 因子定义/代码版本 | FactorSpec.id + schema_version(expression 编译指纹) |
| 输入快照集合 | artifact 的 source_snapshot_ids(#391-#394 完成事实) |
| cutoff / 证券池 | artifact manifest 的 knowledge_cutoff + universe 声明 |
| 计算参数 | DerivedSpecRecord 参数集 |
| 输出 checksum | DerivedVersionRecord 内容寻址 |

同名因子读到不同语义 = 身份任一维度不同 = 不同 artifact,不共享缓存。

## 3. 发布/失败/恢复语义

- **完成才可读**:artifact 写入+校验后记录 COMPLETE(复用 #393 三阶段
  checkpoint 语义:PLANNED→PAYLOAD_COMMITTED→COMPLETE),部分失败停留
  可恢复态,读取侧经 snapshot_readiness 同款检查。
- **重试**:同身份同 checksum 幂等复用;同身份不同 checksum 拒绝(修订
  走新版本号,不覆盖)。
- **无产物时诚实状态**:评估入口返回明确的"无物化输入"缺失原因(同
  #391 SELECTION_DATA_INCOMPLETE 模式),不静默回退即时计算冒充。
- **EOD 空跑/幽灵目录清理**归入实施切片(空跑不产 artifact、不落目录)。

## 4. 刻意不做(最小必要)

- 不建 shadow/certification/失效队列等控制面(#390 评审判零消费者);
  publication_safety(features 自有门禁)保留为唯一发布保护。
- 不强制选股/回测迁移到物化(即时计算继续;迁移由重复计算成本驱动,
  不预造切换开关)。
- 不做在线 serving/多租户/新依赖。

## 5. DQ 盘点与工具取舍

必要规则(已有消费者):schema/类型检查(写入校验)、交易日覆盖(评估
窗口)、跨源口径(#395 对账框架)、PIT 可见性(knowledge_date 列)、失败
处置(fail-closed+可重试)。现有 Polars 表达式实现这些规则的维护成本低于
引入 Pandera 全量替换的迁移成本——**结论:暂不引入 Pandera**,个别复杂
规则(schema 交叉校验)若维护成本实测上升再单独评估。

## 6. 首个实施票验收口径

以"计算→保存→研究/IC 读取"最高可观察入口验收:真实(非夹具)摄取数据
驱动,产非空 artifact,FactorEvaluationFacade 读到并产出含 rank_ic 的
评估报告;反例:身份漂移拒绝、部分写入不可读、无产物明确缺失态。

## 7. 历史设计文档甄别

#280/#274/#273/#272/#271/#270/#202 为设计输入(已逐票评论标注);其
中与本文冲突的认证/治理类内容随 #392 废弃。因子设计文档(docs/research/
因子类)标注"阶段一未重设计物化控制面"。
