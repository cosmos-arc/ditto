import { usePipelines } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { PipelineStatus } from "@/types";

const STATUS_VARIANT_MAP: Record<PipelineStatus, "healthy" | "degraded" | "warning" | "error"> = {
	idle: "healthy",
	running: "healthy",
	success: "healthy",
	warning: "warning",
	failed: "error",
};

const STATUS_LABEL_MAP: Record<PipelineStatus, string> = {
	idle: "空闲",
	running: "运行中",
	success: "成功",
	warning: "警告",
	failed: "失败",
};

export function PipelineTable() {
	const { data, isLoading, isError, refetch } = usePipelines();

	return (
		<ContextSection title="Pipelines & Jobs" count={data?.total} data-info-level="l1" data-info-unit="pipelines">
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "管道数据加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.items.map((pipeline) => (
							<div
								key={pipeline.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{pipeline.name}</span>
									<StatusBadge
										variant={STATUS_VARIANT_MAP[pipeline.status]}
										label={STATUS_LABEL_MAP[pipeline.status]}
										size="sm"
									/>
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span>{pipeline.recordsProcessed.toLocaleString()} 条</span>
									<span>{pipeline.duration}s</span>
									{pipeline.errorCount > 0 && (
										<span className="text-(--color-system-down)">
											{pipeline.errorCount} 错误
										</span>
									)}
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
