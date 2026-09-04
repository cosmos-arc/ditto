import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { StrategyDetail } from "@/types/strategy";
import { useStrategy } from "../hooks/use-strategy";

interface StrategyOverviewProps {
	readonly id: string;
}

interface PipelineNodeView {
	readonly id: string;
	readonly name: string;
	readonly type: string;
}

const PERFORMANCE_LABELS = ["Sharpe", "年化收益", "最大回撤", "胜率"] as const;

/** 从服务端 legacy spec 派生展示顺序，不声称这些节点已执行。 */
function derivePipelineNodes(spec: StrategyDetail["spec"]): PipelineNodeView[] {
	return [
		{ id: "scorer", name: "评分", type: spec.scorer.method },
		{ id: "selector", name: "选取", type: spec.selector.method },
		{ id: "execution", name: "执行", type: spec.execution.method },
		...spec.constraints.map((constraint, index) => ({
			id: `constraint-${constraint.type}-${index}`,
			name: constraint.type,
			type: "约束",
		})),
	];
}

function SurfaceTitle({ title, note }: { readonly title: string; readonly note?: string }) {
	return (
		<header className="flex h-9 items-center justify-between border-b border-(--color-border-subtle) px-3">
			<h2 className="text-xs font-semibold text-(--color-foreground)">{title}</h2>
			{note && <span className="text-xs text-(--color-foreground-tertiary)">{note}</span>}
		</header>
	);
}

function StrategyOverviewContent({ id }: StrategyOverviewProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) return <LoadingSkeleton />;
	if (isError || !data) throw new Error("Failed to load strategy overview");

	const nodes = derivePipelineNodes(data.spec);
	const params = Object.entries(data.spec.params);

	return (
		<div className="flex min-h-full flex-col bg-(--color-surface-1)">
			<section
				aria-label="绩效证据摘要"
				className="grid grid-cols-2 border-b border-(--color-border-subtle) md:grid-cols-4"
			>
				{PERFORMANCE_LABELS.map((label) => (
					<div key={label} className="border-r border-(--color-border-subtle) px-4 py-3 last:border-r-0">
						<p className="text-[11px] text-(--color-foreground-tertiary)">{label}</p>
						<strong className="mt-1 block text-sm font-semibold text-(--color-foreground-secondary)">未评估</strong>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">未绑定回测制品</p>
					</div>
				))}
			</section>

			<div className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_320px]">
				<div className="flex min-w-0 flex-col gap-3">
					<section
						aria-label="策略流程"
						data-info-level="l2"
						data-info-unit="strategy-pipeline"
						className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)"
					>
						<SurfaceTitle title="策略流程" note="定义顺序 · 尚未执行" />
						<ol className="grid gap-px bg-(--color-border-subtle) sm:grid-cols-2 xl:grid-cols-3">
							{nodes.map((node, index) => (
								<li
									key={node.id}
									data-info-level="l3"
									data-info-unit="pipeline-node"
									className="flex min-w-0 items-center gap-3 bg-(--color-surface-2) px-3 py-3"
								>
									<span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-(--color-border) font-data text-xs text-(--color-foreground-tertiary)">
										{index + 1}
									</span>
									<div className="min-w-0">
										<p className="truncate text-xs font-medium text-(--color-foreground)">{node.name}</p>
										<p className="mt-0.5 truncate font-data text-xs text-(--color-foreground-tertiary)">{node.type}</p>
									</div>
								</li>
							))}
						</ol>
					</section>

					<div className="grid gap-3 md:grid-cols-2">
						<section
							aria-label="策略参数"
							data-info-level="l2"
							data-info-unit="strategy-params"
							className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)"
						>
							<SurfaceTitle title="策略参数" note={`${params.length} 项`} />
							{params.length > 0 ? (
								<dl className="divide-y divide-(--color-border-subtle)">
									{params.map(([key, value]) => (
										<div key={key} className="flex items-center justify-between px-3 py-2 text-xs">
											<dt className="font-data text-(--color-foreground-secondary)">{key}</dt>
											<dd className="font-data text-(--color-foreground)">{String(value)}</dd>
										</div>
									))}
								</dl>
							) : (
								<p className="p-3 text-xs text-(--color-foreground-tertiary)">未定义参数。</p>
							)}
						</section>
						<section
							aria-label="风控约束"
							data-info-level="l2"
							data-info-unit="risk-rules"
							className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)"
						>
							<SurfaceTitle title="风控约束" note={`${data.spec.constraints.length} 项`} />
							{data.spec.constraints.length > 0 ? (
								<ul className="divide-y divide-(--color-border-subtle)">
									{data.spec.constraints.map((rule) => (
										<li key={rule.type} className="flex items-center justify-between px-3 py-2 text-xs">
											<span className="font-data text-(--color-foreground-secondary)">{rule.type}</span>
											<span className="text-(--color-led-success)">已定义</span>
										</li>
									))}
								</ul>
							) : (
								<p className="p-3 text-xs text-(--color-foreground-tertiary)">未定义约束。</p>
							)}
						</section>
					</div>
				</div>

				<aside aria-label="策略证据" className="flex min-w-0 flex-col gap-3">
					<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)">
						<SurfaceTitle title="不可变身份" />
						<dl className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-2 p-3 text-xs">
							<dt className="text-(--color-foreground-tertiary)">Strategy ID</dt>
							<dd className="truncate font-data text-(--color-foreground-secondary)" title={data.strategyId}>
								{data.strategyId}
							</dd>
							<dt className="text-(--color-foreground-tertiary)">当前版本</dt>
							<dd className="font-data text-(--color-foreground-secondary)">v{data.version}</dd>
							<dt className="text-(--color-foreground-tertiary)">Universe</dt>
							<dd className="font-data text-(--color-foreground-secondary)">{data.spec.universe || "未设置"}</dd>
							<dt className="text-(--color-foreground-tertiary)">Benchmark</dt>
							<dd className="font-data text-(--color-foreground-secondary)">{data.spec.benchmark || "未设置"}</dd>
							<dt className="text-(--color-foreground-tertiary)">资产类型</dt>
							<dd className="font-data text-(--color-foreground-secondary)">{data.spec.assetClass || "未设置"}</dd>
						</dl>
					</section>
					<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)">
						<SurfaceTitle title="因子表达式" note={`${data.spec.signalExpressions.length} 项`} />
						{data.spec.signalExpressions.length > 0 ? (
							<ul className="divide-y divide-(--color-border-subtle)">
								{data.spec.signalExpressions.map((factor, index) => (
									<li key={factor} className="flex items-center justify-between px-3 py-2 text-xs">
										<span className="font-data text-(--color-foreground-secondary)">{factor}</span>
										<span className="font-data text-(--color-foreground-tertiary)">
											{data.spec.signalWeights[index] ?? "—"}
										</span>
									</li>
								))}
							</ul>
						) : (
							<p className="p-3 text-xs text-(--color-foreground-tertiary)">未定义因子表达式。</p>
						)}
					</section>
					<section className="rounded-(--radius-md) border border-dashed border-(--color-border) p-3">
						<div className="flex items-center justify-between">
							<p className="text-xs font-medium text-(--color-foreground)">回测证据</p>
							<strong className="text-xs text-(--color-foreground-tertiary)">未评估</strong>
						</div>
						<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
							需要实验固定 snapshot、时间范围、registry hash 与策略版本后，才能展示绩效与曲线。
						</p>
					</section>
				</aside>
			</div>
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
