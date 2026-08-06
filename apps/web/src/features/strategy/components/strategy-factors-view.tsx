import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategy } from "../hooks/use-strategy";

interface StrategyFactorsViewProps {
	readonly id: string;
}

function StrategyFactorsViewContent({ id }: StrategyFactorsViewProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data) {
		throw new Error("Failed to load strategy factors");
	}

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<ContextSection title="策略参数">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					{Object.entries(data.spec.params).map(([key, value]) => (
						<li
							key={key}
							className="flex items-center justify-between rounded-sm p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<span>{key}</span>
							<span className="text-(--color-foreground-tertiary)">{String(value)}</span>
						</li>
					))}
				</ul>
			</ContextSection>
		</div>
	);
}

export function StrategyFactorsView(props: StrategyFactorsViewProps) {
	return (
		<DittoErrorBoundary>
			<StrategyFactorsViewContent {...props} />
		</DittoErrorBoundary>
	);
}
