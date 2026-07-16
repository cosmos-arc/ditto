import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategy } from "../hooks/use-strategy";

interface StrategyInspectorProps {
	readonly id: string;
}

function StrategyInspectorContent({ id }: StrategyInspectorProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data) {
		throw new Error("Failed to load strategy parameters");
	}

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<ContextSection title="策略参数">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					<li className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg) rounded-sm">
						<span>股票池</span>
						<span className="text-(--color-foreground-tertiary)">{data.universe}</span>
					</li>
					<li className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg) rounded-sm">
						<span>模式</span>
						<span className="text-(--color-foreground-tertiary)">{data.mode}</span>
					</li>
					{data.factors.map((factor) => (
						<li
							key={factor}
							className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg) rounded-sm"
						>
							<span>{factor}</span>
							<span className="text-(--color-foreground-tertiary)">因子</span>
						</li>
					))}
				</ul>
			</ContextSection>
		</div>
	);
}

export function StrategyInspector(props: StrategyInspectorProps) {
	return (
		<DittoErrorBoundary>
			<StrategyInspectorContent {...props} />
		</DittoErrorBoundary>
	);
}
