import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { StrategyLifecycleState } from "@/types/strategy";
import { useStrategy, useStrategyVersions } from "../hooks";

interface StrategyHeaderProps {
	readonly id: string;
}

const LIFECYCLE_VARIANT: Record<StrategyLifecycleState, "healthy" | "warning" | "error" | "default"> = {
	published: "healthy",
	approved: "healthy",
	draft: "default",
	review: "warning",
	deprecated: "default",
	unknown: "default",
};

export function StrategyHeader({ id }: StrategyHeaderProps) {
	const { data, isLoading, refetch } = useStrategy(id);
	const versions = useStrategyVersions(id);
	const currentVersion = versions.data?.find((version) => version.version === data?.version);

	if (isLoading) {
		return <LoadingSkeleton variant="panel" className="h-16" />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3">
					<div className="flex flex-col">
						<span className="text-lg font-bold">{data.name}</span>
						<span className="text-xs text-(--color-foreground-tertiary)">
							v{data.version} · {data.spec.universe}
						</span>
					</div>
					<StatusBadge variant={LIFECYCLE_VARIANT[data.lifecycleState]} label={data.lifecycleState} size="sm" />
					<div className="flex flex-wrap gap-2">
						{data.tags.map((tag) => (
							<span
								key={tag}
								className="rounded-full bg-(--color-surface-1) px-2 py-0.5 text-xs text-(--color-foreground-secondary)"
							>
								{tag}
							</span>
						))}
					</div>
					<dl className="grid basis-full gap-x-4 gap-y-1 border-t border-(--color-border-subtle) pt-2 text-xs text-(--color-foreground-tertiary) sm:grid-cols-2 xl:grid-cols-4">
						<div>
							<dt className="inline">Spec hash: </dt>
							<dd className="inline font-data break-all">{currentVersion?.specHash ?? "尚未解析"}</dd>
						</div>
						<div>
							<dt className="inline">Certified snapshot: </dt>
							<dd className="inline">未绑定，Experiment preflight 时固定</dd>
						</div>
						<div>
							<dt className="inline">Strategy-eligible start: </dt>
							<dd className="inline">待 preflight 计算</dd>
						</div>
						<div>
							<dt className="inline">R2 Gate: </dt>
							<dd className="inline">创建实验时按 live evidence 硬门禁</dd>
						</div>
					</dl>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
