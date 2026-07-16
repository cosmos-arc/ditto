import { useAgentPlans, useAgentRuns, useAgentFindings } from "../hooks";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { RunStatus } from "@/types";

interface AgentInspectorPanelProps {
	readonly planId?: string;
}

const STATUS_DOT: Record<RunStatus, string> = {
	running: "bg-(--color-led-success)",
	completed: "bg-(--color-accent)",
	warning: "bg-(--color-led-warning)",
	pending: "bg-(--color-foreground-tertiary)",
	failed: "bg-(--color-led-error)",
	cancelled: "bg-(--color-foreground-tertiary)",
};

export function AgentInspectorPanel({ planId }: AgentInspectorPanelProps) {
	const { data: plansData, isLoading: plansLoading } = useAgentPlans();
	const { data: runsData, isLoading: runsLoading } = useAgentRuns();
	const { data: findingsData } = useAgentFindings();

	if (plansLoading || runsLoading) {
		return (
			<Panel>
				<PanelHeader title="计划详情" />
				<PanelBody>
					<div className="p-3">
						<LoadingSkeleton variant="panel" rows={5} />
					</div>
				</PanelBody>
			</Panel>
		);
	}

	if (!planId) {
		return (
			<Panel>
				<PanelHeader title="计划详情" />
				<PanelBody>
					<div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
						<span className="text-(length:--text-sm) text-(--color-foreground-tertiary)">
							选择一个计划查看详情
						</span>
					</div>
				</PanelBody>
			</Panel>
		);
	}

	const plan = plansData?.items.find((p) => p.id === planId);
	const relatedRuns = runsData?.items.filter((r) => r.planId === planId) ?? [];
	const relatedFindings = findingsData?.items.filter((f) =>
		relatedRuns.some((r) => r.id === f.runId),
	) ?? [];

	if (!plan) {
		return (
			<Panel>
				<PanelHeader title="计划详情" />
				<PanelBody>
					<div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
						<span className="text-(length:--text-sm) text-(--color-foreground-tertiary)">
							计划未找到
						</span>
					</div>
				</PanelBody>
			</Panel>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ title: "计划详情加载失败" }}>
			<Panel>
				<PanelHeader title={plan.name} />
				<PanelBody>
					<div className="flex flex-col gap-(--density-gutter) p-3">
						<section data-info-level="l1" data-info-unit="agent-objective">
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
								目标
							</h4>
							<p className="text-(length:--text-sm) text-(--color-foreground)">
								{plan.objective}
							</p>
						</section>

						{plan.constraints.length > 0 && (
							<section data-info-level="l1" data-info-unit="agent-constraints">
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
									约束条件
								</h4>
								<ul className="flex flex-col gap-0.5">
									{plan.constraints.map((c) => (
										<li
											key={c}
											className="text-(length:--text-sm) text-(--color-foreground-tertiary)"
										>
											• {c}
										</li>
									))}
								</ul>
							</section>
						)}

						{plan.scope.length > 0 && (
							<section data-info-level="l1" data-info-unit="agent-scope">
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
									范围
								</h4>
								<div className="flex flex-wrap gap-1">
									{plan.scope.map((s) => (
										<span
											key={s}
											className="rounded-(--radius-sm) bg-(--color-surface-strip) px-2 py-0.5 text-(length:--text-sm) text-(--color-foreground-secondary)"
										>
											{s}
										</span>
									))}
								</div>
							</section>
						)}

						{relatedRuns.length > 0 && (
							<section data-info-level="l1" data-info-unit="agent-run-status">
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
									运行状态
								</h4>
								<ul className="flex flex-col gap-1">
									{relatedRuns.map((run) => (
										<li
											key={run.id}
											className="flex items-center gap-2 text-(length:--text-sm)"
										>
											<span
												className={[
													"h-1.5 w-1.5 shrink-0 rounded-full",
													STATUS_DOT[run.status as RunStatus] ?? STATUS_DOT.pending,
												].join(" ")}
											/>
											<span className="text-(--color-foreground)">
												{run.stage}
											</span>
											<span className="ml-auto font-data text-(--color-foreground-tertiary)">
												{run.progress}%
											</span>
										</li>
									))}
								</ul>
							</section>
						)}

						{relatedFindings.length > 0 && (
							<section data-info-level="l2" data-info-unit="agent-related-findings">
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
									相关发现
								</h4>
								<ul className="flex flex-col gap-1">
									{relatedFindings.slice(0, 5).map((finding) => (
										<li
											key={finding.id}
											className="text-(length:--text-sm) text-(--color-foreground-tertiary)"
										>
											{finding.text.slice(0, 80)}
											{finding.text.length > 80 ? "…" : ""}
										</li>
									))}
								</ul>
							</section>
						)}
					</div>
				</PanelBody>
			</Panel>
		</DittoErrorBoundary>
	);
}
