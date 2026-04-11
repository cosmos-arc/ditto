import { useProviders } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function ProviderTable() {
	const { data, isLoading, isError, refetch } = useProviders();

	return (
		<ContextSection title="Data Providers" count={data?.providers.length}>
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "数据提供者加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.providers.map((provider) => (
							<div
								key={provider.name}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{provider.name}</span>
									<StatusBadge
										variant={
											provider.status === "healthy"
												? "healthy"
												: provider.status === "degraded"
													? "degraded"
													: "error"
										}
										label={provider.statusText ?? provider.status}
										size="sm"
									/>
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span>{provider.latency}ms</span>
									<span>
										缺失 {((provider.missingRate ?? 0) * 100).toFixed(1)}%
									</span>
									<span>
										异常 {((provider.anomalyRate ?? 0) * 100).toFixed(1)}%
									</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
