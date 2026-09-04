import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { StrategySpec } from "@/types/strategy";
import { ParamFields } from "./param-fields";
import { NumberField, TextField } from "./spec-fields";

interface StrategySpecFormProps {
	readonly spec: StrategySpec;
	/** 工作副本更新器（与 `useStrategyStudioStore.updateSpec` 同构）。 */
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
}

/**
 * 策略定义表单（legacy spec_json 的核心字段编辑）。
 *
 * 编辑顶层标量 + scorer/selector 单例槽位（method + params）+ execution（频率/方法/下单类型 +
 * cost_model）。每次编辑通过 `onChange(updater)` 上抛不可变更新；constraints 数组的完整
 * CRUD 由 {@link ConstraintsPipeline} 负责，本表单不触及。
 */
export function StrategySpecForm({ spec, onChange }: StrategySpecFormProps): ReactElement {
	return (
		<div className="grid grid-cols-1 gap-3 xl:grid-cols-2 [&>*:last-child]:xl:col-span-2">
			<ContextSection title="基本信息">
				<div className="grid grid-cols-2 gap-2 p-(--density-panel-padding)">
					<TextField label="名称" value={spec.name} onChange={(v) => onChange((d) => ({ ...d, name: v }))} />
					<TextField label="模板" value={spec.template} onChange={(v) => onChange((d) => ({ ...d, template: v }))} />
					<TextField label="股票池" value={spec.universe} onChange={(v) => onChange((d) => ({ ...d, universe: v }))} />
					<TextField
						label="资产类别"
						value={spec.assetClass}
						onChange={(v) => onChange((d) => ({ ...d, assetClass: v }))}
					/>
					<TextField label="基准" value={spec.benchmark} onChange={(v) => onChange((d) => ({ ...d, benchmark: v }))} />
				</div>
			</ContextSection>

			<ContextSection title="评分 / 选取">
				<div className="grid grid-cols-2 gap-2 p-(--density-panel-padding)">
					<TextField
						label="评分方法"
						value={spec.scorer.method}
						onChange={(v) => onChange((d) => ({ ...d, scorer: { ...d.scorer, method: v } }))}
					/>
					<ParamFields
						params={spec.scorer.params}
						onChange={(p) => onChange((d) => ({ ...d, scorer: { ...d.scorer, params: p } }))}
					/>
					<TextField
						label="选取方法"
						value={spec.selector.method}
						onChange={(v) => onChange((d) => ({ ...d, selector: { ...d.selector, method: v } }))}
					/>
					<ParamFields
						params={spec.selector.params}
						onChange={(p) => onChange((d) => ({ ...d, selector: { ...d.selector, params: p } }))}
					/>
				</div>
			</ContextSection>

			<ContextSection title="执行假设">
				<div className="grid grid-cols-2 gap-2 p-(--density-panel-padding) xl:grid-cols-3">
					<TextField
						label="频率"
						value={spec.execution.frequency}
						onChange={(v) => onChange((d) => ({ ...d, execution: { ...d.execution, frequency: v } }))}
					/>
					<TextField
						label="执行方法"
						value={spec.execution.method}
						onChange={(v) => onChange((d) => ({ ...d, execution: { ...d.execution, method: v } }))}
					/>
					<TextField
						label="下单类型"
						value={spec.execution.defaultOrderType}
						onChange={(v) => onChange((d) => ({ ...d, execution: { ...d.execution, defaultOrderType: v } }))}
					/>
					<NumberField
						label="佣金费率"
						value={spec.execution.costModel?.commissionRate ?? 0}
						onChange={(v) =>
							onChange((d) => ({
								...d,
								execution: { ...d.execution, costModel: { ...d.execution.costModel, commissionRate: v } },
							}))
						}
					/>
					<NumberField
						label="滑点(bps)"
						value={spec.execution.costModel?.slippageBps ?? 0}
						onChange={(v) =>
							onChange((d) => ({
								...d,
								execution: { ...d.execution, costModel: { ...d.execution.costModel, slippageBps: v } },
							}))
						}
					/>
					<TextField
						label="冲击模型"
						value={spec.execution.costModel?.impactModel ?? ""}
						onChange={(v) =>
							onChange((d) => ({
								...d,
								execution: { ...d.execution, costModel: { ...d.execution.costModel, impactModel: v } },
							}))
						}
					/>
				</div>
			</ContextSection>
		</div>
	);
}
