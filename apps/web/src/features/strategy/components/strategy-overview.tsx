import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { StrategyDetail } from "@/types/strategy";
import { useStrategy } from "../hooks/use-strategy";

interface StrategyOverviewProps {
	readonly id: string;
}

interface PipelineNodeView {
	readonly id: string;
	readonly name: string;
	readonly type: string;
}

/** 从 legacy spec（scorer/selector/execution/constraints）派生有序流水线节点。 */
function derivePipelineNodes(spec: StrategyDetail["spec"]): PipelineNodeView[] {
	return [
		{ id: "scorer", name: "评分", type: spec.scorer.method },
		{ id: "selector", name: "选取", type: spec.selector.method },
		{ id: "execution", name: "执行", type: spec.execution.method },
		...spec.constraints.map((constraint, index) => ({
			id: `constraint-${constraint.type}-${index}`,
			name: constraint.type,
			type: "constraint",
		})),
	];
}

function StrategyOverviewContent({ id }: StrategyOverviewProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data) {
		throw new Error("Failed to load strategy overview");
	}

	const nodes = derivePipelineNodes(data.spec);

	return (
		<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
			<div data-info-level="l2" data-info-unit="strategy-pipeline">
				<ContextSection title="策略流程">
					<ul className="flex flex-col gap-(--section-gap)">
						{nodes.map((node) => (
							<li
								key={node.id}
								data-info-level="l3"
								data-info-unit="pipeline-node"
								className="flex items-center justify-between rounded-sm p-(--density-panel-padding) hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span>{node.name}</span>
								<span className="text-sm text-(--color-foreground-tertiary)">{node.type}</span>
							</li>
						))}
					</ul>
				</ContextSection>
			</div>

			<div data-info-level="l2" data-info-unit="strategy-params">
				<ContextSection title="策略参数">
					<ul className="flex flex-col gap-(--section-gap)">
						{Object.entries(data.spec.params).map(([key, value]) => (
							<li
								key={key}
								className="flex items-center justify-between rounded-sm p-(--density-panel-padding) hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span>{key}</span>
								<span className="text-(--color-foreground-tertiary)">{String(value)}</span>
							</li>
						))}
					</ul>
				</ContextSection>
			</div>

			<div data-info-level="l2" data-info-unit="risk-rules">
				<ContextSection title="风控约束">
					<ul className="flex flex-col gap-(--section-gap)">
						{data.spec.constraints.map((rule) => (
							<li
								key={rule.type}
								className="flex items-center justify-between rounded-sm p-(--density-panel-padding) hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span>{rule.type}</span>
								<span className="text-(--color-led-success)">启用</span>
							</li>
						))}
					</ul>
				</ContextSection>
			</div>
		</div>
	);
}

export function StrategyOverview(props: StrategyOverviewProps) {
	return (
		<DittoErrorBoundary>
			<StrategyOverviewContent {...props} />
		</DittoErrorBoundary>
	);
}
