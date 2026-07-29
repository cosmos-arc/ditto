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
					<li className="flex items-center justify-between rounded-sm p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg)">
						<span>股票池</span>
						<span className="text-(--color-foreground-tertiary)">{data.spec.universe}</span>
					</li>
					<li className="flex items-center justify-between rounded-sm p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg)">
						<span>模板</span>
						<span className="text-(--color-foreground-tertiary)">{data.spec.template}</span>
					</li>
					<li className="flex items-center justify-between rounded-sm p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg)">
						<span>资产类别</span>
						<span className="text-(--color-foreground-tertiary)">{data.spec.assetClass}</span>
					</li>
					{data.tags.map((tag) => (
						<li
							key={tag}
							className="flex items-center justify-between rounded-sm p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<span>{tag}</span>
							<span className="text-(--color-foreground-tertiary)">标签</span>
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
