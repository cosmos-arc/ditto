import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { ConstraintSpec, StrategySpec } from "@/types/strategy";
import { ParamFields } from "./param-fields";
import { TextField } from "./spec-fields";

interface NodeInspectorProps {
	readonly spec: StrategySpec;
	readonly selectedKey: string | null;
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
}

function parseConstraintIndex(key: string | null): number | null {
	if (!key?.startsWith("constraint-")) return null;
	const index = Number(key.slice("constraint-".length));
	return Number.isInteger(index) ? index : null;
}

function updateConstraint(
	index: number,
	change: (constraint: ConstraintSpec) => ConstraintSpec,
): (draft: StrategySpec) => StrategySpec {
	return (draft) => ({
		...draft,
		constraints: draft.constraints.map((constraint, i) => (i === index ? change(constraint) : constraint)),
	});
}

function OverviewRow({ label, value }: { readonly label: string; readonly value: string }): ReactElement {
	return (
		<li className="flex items-center justify-between rounded-sm p-(--density-panel-padding) hover:bg-(--color-interaction-hover-subtle-bg)">
			<span>{label}</span>
			<span className="text-(--color-foreground-tertiary)">{value}</span>
		</li>
	);
}

/**
 * 节点检查器（Studio inspector slot）。
 *
 * 选中约束（`constraint-N`，来自 ConstraintsPipeline）时编辑其 type + params；否则显示策略
 * 概览（universe/template/assetClass + params 键值，只读）。scorer/selector 单例槽位的
 * method + params 在 {@link StrategySpecForm} 编辑，本组件只处理约束配置。
 */
export function NodeInspector({ spec, selectedKey, onChange }: NodeInspectorProps): ReactElement {
	const constraintIndex = parseConstraintIndex(selectedKey);
	const selected = constraintIndex !== null ? spec.constraints[constraintIndex] : null;

	if (selected && constraintIndex !== null) {
		return (
			<ContextSection title={`约束 ${constraintIndex + 1}`}>
				<div className="flex flex-col gap-2 p-(--density-panel-padding)">
					<TextField
						label="约束类型"
						value={selected.type}
						onChange={(value) => onChange(updateConstraint(constraintIndex, (c) => ({ ...c, type: value })))}
					/>
					<ParamFields
						params={selected.params}
						onChange={(params) => onChange(updateConstraint(constraintIndex, (c) => ({ ...c, params })))}
					/>
				</div>
			</ContextSection>
		);
	}

	return (
		<ContextSection title="策略参数">
			<ul className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
				<OverviewRow label="股票池" value={spec.universe} />
				<OverviewRow label="模板" value={spec.template} />
				<OverviewRow label="资产类别" value={spec.assetClass} />
				{Object.entries(spec.params).map(([key, value]) => (
					<OverviewRow key={key} label={key} value={String(value)} />
				))}
			</ul>
		</ContextSection>
	);
}
