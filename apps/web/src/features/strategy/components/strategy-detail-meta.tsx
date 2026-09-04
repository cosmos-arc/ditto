import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { ApiError } from "@/lib/api-client";
import type { StrategyLifecycleState } from "@/types/strategy";
import { useStrategy } from "../hooks";

interface StrategyDetailMetaProps {
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

export function StrategyDetailMeta({ id }: StrategyDetailMetaProps) {
	const { data, isLoading, error, refetch } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton variant="panel" className="h-9" />;
	}

	if (error) {
		return (
			<div className="flex h-9 items-center gap-3 px-4 text-xs text-(--color-led-danger)">
				<p role="alert">
					{error instanceof ApiError
						? `${error.status} ${error.errorCode ?? "STRATEGY_DETAIL_ERROR"}: ${error.message}`
						: error.message}
				</p>
				<button type="button" className="underline" onClick={() => void refetch()}>
					重试策略详情
				</button>
			</div>
		);
	}

	if (!data)
		return (
			<div className="flex h-9 items-center px-4 text-xs text-(--color-foreground-tertiary)">
				策略不存在或服务端未返回定义。
			</div>
		);

	return (
		<div className="flex h-9 min-h-9 items-center gap-3 overflow-hidden bg-(--color-surface-1) px-4 text-[11px]">
			<div className="flex min-w-0 items-center gap-2">
				<h1 className="max-w-64 truncate text-sm font-semibold text-(--color-foreground)">{data.name}</h1>
				<StatusBadge variant={LIFECYCLE_VARIANT[data.lifecycleState]} label={data.lifecycleState} size="sm" />
				<span className="truncate font-data text-(--color-foreground-tertiary)">
					{data.strategyId} · v{data.version} · {data.spec.universe}
				</span>
			</div>
			<span className="h-4 w-px shrink-0 bg-(--color-border-subtle)" aria-hidden="true" />
			<dl className="flex shrink-0 items-center gap-4">
				<div className="flex items-center gap-1">
					<dt className="text-(--color-foreground-tertiary)">创建</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{data.createdAt.slice(0, 10)}</dd>
				</div>
				<div className="flex items-center gap-1">
					<dt className="text-(--color-foreground-tertiary)">模板</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{data.spec.template || "未设置"}</dd>
				</div>
				<div className="flex items-center gap-1">
					<dt className="text-(--color-foreground-tertiary)">因子</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{data.spec.signalExpressions.length}</dd>
				</div>
				<div className="flex items-center gap-1">
					<dt className="text-(--color-foreground-tertiary)">风控规则</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{data.spec.constraints.length}</dd>
				</div>
			</dl>
			<div className="ml-auto flex shrink-0 gap-1.5">
				{data.tags.map((tag) => (
					<span
						key={tag}
						className="rounded-sm bg-(--color-surface-2) px-1.5 py-0.5 text-xs text-(--color-foreground-secondary)"
					>
						{tag}
					</span>
				))}
			</div>
		</div>
	);
}
