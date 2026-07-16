import { useStrategy } from "../hooks/use-strategy";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ContextSection } from "@/components/domain/context-section";

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
			<ContextSection title="因子配置">
				<ul className="flex flex-col gap-[var(--section-gap)]">
					{data.factors.map((factor) => {
						const weight = data.weightConfig[factor];
						return (
							<li
								key={factor}
								className="flex items-center justify-between p-[var(--density-panel-padding)] hover:bg-(--color-interaction-hover-subtle-bg) rounded-sm"
							>
								<span>{factor}</span>
								<span className="text-(--color-foreground-tertiary)">
									{weight !== undefined ? `${(weight * 100).toFixed(0)}%` : "—"}
								</span>
							</li>
						);
					})}
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
