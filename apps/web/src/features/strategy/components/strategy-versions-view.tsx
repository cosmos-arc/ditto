import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategyVersions } from "../hooks";

interface StrategyVersionsViewProps {
	readonly id: string;
}

export function StrategyVersionsView({ id }: StrategyVersionsViewProps) {
	const { data, isLoading, refetch } = useStrategyVersions(id);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={5} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="p-4">
					<ContextSection title="版本历史" count={data.versions.length}>
						<div className="space-y-1">
							{data.versions.map((ver) => (
								<div
									key={ver.version}
									className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center gap-3">
										<span className="font-medium">v{ver.version}</span>
										<span className="text-(--color-foreground-tertiary)">{ver.changeNote}</span>
									</div>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{new Date(ver.savedAt).toLocaleDateString("zh-CN")}
									</span>
								</div>
							))}
						</div>
					</ContextSection>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
