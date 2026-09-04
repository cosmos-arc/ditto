import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { AgentContextActions } from "@/features/agent";
import type { NodeDescriptorView, SpecValidation, StrategyDetail, StrategySpec } from "@/types/strategy";
import { NodeInspector } from "./strategy-inspector";

interface StrategyStudioInspectorProps {
	readonly descriptors: readonly NodeDescriptorView[];
	readonly detail: StrategyDetail;
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
	readonly selectedKey: string | null;
	readonly spec: StrategySpec;
	readonly specHash: string | null;
	readonly validation: SpecValidation | null;
	readonly validationIsStale: boolean;
}

function EvidenceRow({ label, value }: { readonly label: string; readonly value: string }) {
	return (
		<div className="flex items-start justify-between gap-3">
			<dt className="shrink-0 text-(--color-foreground-tertiary)">{label}</dt>
			<dd className="break-all text-right font-data text-(--color-foreground-secondary)">{value}</dd>
		</div>
	);
}

export function StrategyStudioInspector({
	descriptors,
	detail,
	onChange,
	selectedKey,
	spec,
	specHash,
	validation,
	validationIsStale,
}: StrategyStudioInspectorProps) {
	const weightTotal = spec.signalWeights.reduce((sum, value) => sum + value, 0);
	const validationReady = validation !== null && !validationIsStale;

	return (
		<div className="flex flex-col">
			<section aria-label="策略身份与证据" className="border-b border-(--color-border-subtle) p-3">
				<div className="mb-3 flex items-center justify-between gap-2">
					<div>
						<h2 className="text-sm font-semibold text-(--color-foreground)">{detail.name}</h2>
						<p className="font-data text-xs text-(--color-foreground-tertiary)">
							{detail.strategyId} · v{detail.version}
						</p>
					</div>
					<StatusBadge
						variant={detail.lifecycleState === "deprecated" ? "default" : "healthy"}
						label={detail.lifecycleState}
					/>
				</div>
				<dl className="space-y-2 text-[11px]">
					<EvidenceRow label="Spec hash" value={specHash ?? "尚未解析"} />
					<EvidenceRow label="Candidate" value={validationReady ? validation.canonicalHash : "尚未校验"} />
					<EvidenceRow label="Snapshot" value="未绑定，Experiment preflight 时固定" />
					<EvidenceRow label="Eligible start" value="待 preflight 计算" />
				</dl>
				<div className="mt-3 grid grid-cols-3 gap-2 border-t border-(--color-border-subtle) pt-3 text-center text-xs">
					<div>
						<strong className="block font-data text-sm text-(--color-foreground)">
							{spec.signalExpressions.length}
						</strong>
						<span className="text-(--color-foreground-tertiary)">因子</span>
					</div>
					<div>
						<strong className="block font-data text-sm text-(--color-foreground)">{weightTotal.toFixed(2)}</strong>
						<span className="text-(--color-foreground-tertiary)">权重合计</span>
					</div>
					<div>
						<strong className="block font-data text-sm text-(--color-foreground)">{spec.constraints.length}</strong>
						<span className="text-(--color-foreground-tertiary)">约束</span>
					</div>
				</div>
			</section>
			<div className="border-b border-(--color-border-subtle) p-3">
				<p className="mb-2 text-[11px] font-medium text-(--color-foreground-secondary)">治理型 Agent</p>
				<AgentContextActions
					contextType="strategy-version"
					contextId={`${detail.strategyId}@${detail.version}`}
					evidenceObjective="复核当前策略版本的证据、风险与不确定性"
					authorObjective="提出当前策略版本的结构化字段变更草案，并附验证与证据"
				/>
			</div>
			<NodeInspector spec={spec} descriptors={descriptors} selectedKey={selectedKey} onChange={onChange} />
		</div>
	);
}
