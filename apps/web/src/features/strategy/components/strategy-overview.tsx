import { useStrategy } from "../hooks/use-strategy";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ContextSection } from "@/components/domain/context-section";

interface StrategyOverviewProps {
	readonly id: string;
}

function StrategyOverviewContent({ id }: StrategyOverviewProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data) {
		throw new Error("Failed to load strategy overview");
	}

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<ContextSection title="策略流程">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					{data.pipeline.nodes.map((node) => (
						<li
							key={node.id}
							className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-surface-hover) rounded-sm"
						>
							<span>{node.name}</span>
							<span className="text-(--color-foreground-tertiary) text-sm">
								{node.type}
							</span>
						</li>
					))}
				</ul>
			</ContextSection>

			<ContextSection title="因子权重">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					{Object.entries(data.weightConfig).map(([factor, weight]) => (
						<li
							key={factor}
							className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-surface-hover) rounded-sm"
						>
							<span>{factor}</span>
							<span className="text-(--color-foreground-tertiary)">
								{(weight * 100).toFixed(0)}%
							</span>
						</li>
					))}
				</ul>
			</ContextSection>

			<ContextSection title="风控规则">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					{data.riskRules.map((rule) => (
						<li
							key={rule.name}
							className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-surface-hover) rounded-sm"
						>
							<span>{rule.name}</span>
							<span
								className={
									rule.enabled
										? "text-(--color-led-success)"
										: "text-(--color-foreground-tertiary)"
								}
							>
								{rule.enabled ? "启用" : "禁用"}
							</span>
						</li>
					))}
				</ul>
			</ContextSection>
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
