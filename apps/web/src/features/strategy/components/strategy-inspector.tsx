import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { NodeDescriptorView, StrategySpec } from "@/types/strategy";
import { buildStrategyPipeline, updatePipelineNodeConfig } from "../api/pipeline-model";
import { INPUT_CLASS, NumberField, TextField } from "./spec-fields";

interface NodeInspectorProps {
	readonly spec: StrategySpec;
	readonly descriptors: readonly NodeDescriptorView[];
	readonly selectedKey: string | null;
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
}

function OverviewRow({ label, value }: { readonly label: string; readonly value: string }): ReactElement {
	return (
		<li className="flex items-center justify-between rounded-(--radius-sm) p-(--density-panel-padding) hover:bg-(--color-interaction-hover-subtle-bg)">
			<span>{label}</span>
			<span className="font-data text-(--color-foreground-tertiary)">{value}</span>
		</li>
	);
}

function JsonField({
	label,
	value,
	onChange,
}: {
	readonly label: string;
	readonly value: unknown;
	readonly onChange: (value: unknown) => void;
}) {
	return (
		<label className="flex flex-col gap-1 text-(length:--text-sm)">
			<span className="text-(--color-foreground-secondary)">{label}</span>
			<textarea
				aria-label={label}
				key={JSON.stringify(value)}
				defaultValue={JSON.stringify(value, null, 2)}
				className={`${INPUT_CLASS} min-h-24 resize-y`}
				onBlur={(event) => {
					try {
						onChange(JSON.parse(event.target.value) as unknown);
					} catch {
						event.target.setCustomValidity("请输入有效 JSON");
						event.target.reportValidity();
					}
				}}
			/>
		</label>
	);
}

function BooleanField({
	label,
	value,
	onChange,
}: {
	readonly label: string;
	readonly value: boolean;
	readonly onChange: (value: boolean) => void;
}) {
	return (
		<label className="flex items-center justify-between gap-2 text-sm text-(--color-foreground-secondary)">
			<span>{label}</span>
			<input type="checkbox" aria-label={label} checked={value} onChange={(event) => onChange(event.target.checked)} />
		</label>
	);
}

/** Descriptor schema 是配置字段唯一来源；unknown descriptor 只读显示原始配置。 */
export function NodeInspector({ spec, descriptors, selectedKey, onChange }: NodeInspectorProps): ReactElement {
	const node = buildStrategyPipeline(spec, descriptors).find((candidate) => candidate.key === selectedKey) ?? null;

	if (!node) {
		return (
			<ContextSection title="策略参数">
				<ul className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<OverviewRow label="股票池" value={spec.universe} />
					<OverviewRow label="模板" value={spec.template} />
					<OverviewRow label="资产类别" value={spec.assetClass} />
				</ul>
			</ContextSection>
		);
	}

	if (!node.descriptor || node.readOnly) {
		return (
			<ContextSection title="未知 descriptor">
				<div className="flex flex-col gap-2 p-(--density-panel-padding)">
					<p className="text-sm text-(--color-led-warning)">
						{node.identity} 未在当前 registry 中注册，只读且不可删除。
					</p>
					<pre className="overflow-auto rounded-(--radius-sm) bg-(--color-surface-muted) p-2 text-xs">
						<code>{JSON.stringify(node.config, null, 2)}</code>
					</pre>
				</div>
			</ContextSection>
		);
	}
	const selectedNode = node;

	function update(key: string, value: unknown): void {
		onChange((draft) => updatePipelineNodeConfig(draft, selectedNode, key, value));
	}

	return (
		<ContextSection title={node.displayName}>
			<div className="flex flex-col gap-2 p-(--density-panel-padding)">
				<p className="font-data text-xs text-(--color-foreground-tertiary)">{node.identity}</p>
				{Object.entries(node.descriptor.configSchema).map(([key, type]) => {
					const value = node.config[key] ?? node.descriptor?.defaultConfig[key];
					if (type === "number" || type === "integer") {
						return (
							<NumberField
								key={key}
								label={key}
								value={typeof value === "number" ? value : 0}
								onChange={(next) => update(key, next)}
							/>
						);
					}
					if (type === "boolean") {
						return <BooleanField key={key} label={key} value={value === true} onChange={(next) => update(key, next)} />;
					}
					if (type === "string" || type === "string_or_null") {
						return (
							<TextField
								key={key}
								label={key}
								value={typeof value === "string" ? value : ""}
								onChange={(next) => update(key, next || (type === "string_or_null" ? null : ""))}
							/>
						);
					}
					return <JsonField key={key} label={key} value={value ?? null} onChange={(next) => update(key, next)} />;
				})}
			</div>
		</ContextSection>
	);
}
