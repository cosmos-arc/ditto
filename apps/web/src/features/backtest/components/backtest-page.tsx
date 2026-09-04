import { useParams } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useState } from "react";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentContextActions } from "@/features/agent";
import { ObjectHubLayout, ShellHeaderExtension } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import { useBacktestReport, useBacktestRun } from "../hooks";
import { BacktestAuditView } from "./backtest-audit-view";
import { BacktestKpiStrip } from "./backtest-kpi-strip";
import { type BacktestOverlayId, BacktestOverlays, backtestActions } from "./backtest-overlays";
import { BacktestOverview } from "./backtest-overview";
import { BacktestReturnsView } from "./backtest-returns-view";
import { BacktestTrades } from "./backtest-trades";

type BacktestTab = "overview" | "report" | "trades" | "audit";

function statusVariant(status: string): "healthy" | "warning" | "critical" | "idle" {
	switch (status.toLowerCase()) {
		case "completed":
			return "healthy";
		case "running":
		case "pending":
			return "warning";
		case "failed":
		case "cancelled":
			return "critical";
		default:
			return "idle";
	}
}

function WorkbenchPanel({
	children,
	description,
	title,
}: {
	readonly children: ReactNode;
	readonly description: string;
	readonly title: string;
}) {
	return (
		<section className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 p-(--density-panel-padding)">
			<header className="border-b border-(--color-border-subtle) pb-2">
				<h2 className="text-sm font-semibold text-(--color-foreground)">{title}</h2>
				<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">{description}</p>
			</header>
			{children}
		</section>
	);
}

export function BacktestPage() {
	const { id } = useParams({ strict: false }) as { id?: string };
	const runId = id ?? "";
	const runQuery = useBacktestRun(runId);
	const reportQuery = useBacktestReport(runQuery.isSuccess ? runId : "");
	const [tab, setTab] = useState<BacktestTab>("overview");
	const [activeOverlay, setActiveOverlay] = useState<BacktestOverlayId | null>(null);

	if (runQuery.isLoading) {
		return (
			<section aria-label="回测结果工作台" className="h-full min-h-0 p-4 text-sm text-(--color-foreground-tertiary)">
				正在加载回测运行…
			</section>
		);
	}

	if (runQuery.error || !runQuery.data) {
		const error = runQuery.error;
		const message = error
			? error instanceof ApiError
				? `${error.status} ${error.errorCode ?? "BACKTEST_RUN_ERROR"}: ${error.message}`
				: error.message
			: "回测运行不存在";
		return (
			<section aria-label="回测结果工作台" className="flex h-full min-h-0 items-center justify-center p-4">
				<div className="flex w-full max-w-xl flex-col gap-2 rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-sm">
					<p role="alert" className="text-(--color-led-danger)">
						{message}
					</p>
					<p className="text-xs text-(--color-foreground-tertiary)">
						运行身份未确认前，不展示绩效、净值、成交或审计数据。
					</p>
					<Button size="sm" variant="outline" className="self-start" onClick={() => void runQuery.refetch()}>
						重试回测运行
					</Button>
				</div>
			</section>
		);
	}

	const run = runQuery.data;
	const report = reportQuery.data;

	function exportReport(): void {
		const payload = JSON.stringify({ report: report ?? null, run }, null, 2);
		const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
		const link = document.createElement("a");
		link.href = url;
		link.download = `${run.runId}-report.json`;
		link.click();
		URL.revokeObjectURL(url);
		setActiveOverlay(null);
	}

	return (
		<section aria-label="回测结果工作台" className="h-full min-h-0">
			<ShellHeaderExtension>
				<div className="ml-auto flex min-w-0 items-center gap-2 overflow-hidden">
					<PageActionBar ariaLabel="回测结果操作" actions={backtestActions} onOpen={setActiveOverlay} />
					<AgentContextActions
						className="flex shrink-0 items-center gap-1.5"
						contextType="backtest-run"
						contextId={`${run.runId}:${run.strategyId}@${run.strategyVersion}`}
						evidenceObjective="复核当前回测运行的报告、净值、基准、成交与审计证据"
					/>
				</div>
			</ShellHeaderExtension>
			<Tabs value={tab} onValueChange={(value) => setTab(value as BacktestTab)} className="h-full min-h-0 gap-0">
				<ObjectHubLayout
					className="grid-rows-[92px_45px_minmax(0,1fr)_36px]"
					meta={
						<div data-testid="backtest-detail-meta" data-info-level="l1" data-info-unit="backtest-meta">
							<div
								data-testid="backtest-detail-identity"
								className="flex h-9 min-w-0 items-center gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
							>
								<h1 className="shrink-0 text-sm font-semibold">Backtest {run.runId}</h1>
								<StatusBadge label={run.status} variant={statusVariant(run.status)} size="sm" />
								<span className="shrink-0 font-data text-xs text-(--color-foreground-secondary)">
									{run.progressPct}%
								</span>
								<span aria-hidden="true" className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
								<span className="min-w-0 truncate font-data text-xs text-(--color-foreground-tertiary)">
									{run.strategyId} · v{run.strategyVersion || "—"} · {run.currentStep || "step 未报告"}
								</span>
								<span className="ml-auto shrink-0 font-data text-xs text-(--color-foreground-tertiary)">
									{run.completedDays}/{run.totalDays || "—"} DAYS
								</span>
							</div>
							<BacktestKpiStrip jobId={runId} />
						</div>
					}
					tabs={
						<nav
							aria-label="回测结果导航"
							data-testid="backtest-detail-tabs"
							data-info-level="l1"
							data-info-unit="backtest-tabs"
							className="h-[45px] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<TabsList variant="line" className="h-full" aria-label="回测结果视图">
								<TabsTrigger value="overview">净值</TabsTrigger>
								<TabsTrigger value="report">收益报告</TabsTrigger>
								<TabsTrigger value="trades">成交</TabsTrigger>
								<TabsTrigger value="audit">审计证据</TabsTrigger>
							</TabsList>
						</nav>
					}
					main={
						<>
							<TabsContent value="overview" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel title="净值证据" description="策略与基准资源独立加载；基准缺失不会改写策略净值。">
									<div data-info-level="l1" data-info-unit="backtest-overview">
										<BacktestOverview jobId={runId} />
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="report" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="收益与统计"
									description="仅展示已发布 report 的元数据、Alpha 与成交汇总，不从净值曲线重算。"
								>
									<div data-info-level="l1" data-info-unit="backtest-returns">
										<BacktestReturnsView jobId={runId} />
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="trades" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="成交记录"
									description="标的名称未进入公共契约时保留 instrument ID，不推断证券名称。"
								>
									<div data-info-level="l1" data-info-unit="backtest-trades">
										<BacktestTrades jobId={runId} />
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="audit" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="运行审计"
									description="逐条保留 record type、instrument identity 与原始 payload。"
								>
									<div data-info-level="l1" data-info-unit="backtest-audit">
										<BacktestAuditView jobId={runId} />
									</div>
								</WorkbenchPanel>
							</TabsContent>
						</>
					}
					bottom={
						<div
							data-testid="backtest-detail-bottom"
							data-info-level="l1"
							data-info-unit="backtest-identity"
							className="flex h-9 min-w-0 items-center gap-3 overflow-hidden border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 font-data text-xs text-(--color-foreground-tertiary)"
						>
							<span className="shrink-0">RUN {run.runId}</span>
							<span aria-hidden="true">·</span>
							<span className="min-w-0 truncate">
								{run.strategyId} @ v{run.strategyVersion || "—"}
							</span>
							<span aria-hidden="true">·</span>
							<span className="shrink-0">
								{report?.periodStart || "期间 未发布"} → {report?.periodEnd || "未发布"}
							</span>
							<span className="ml-auto hidden shrink-0 xl:inline">started {run.startedAt || "未报告"}</span>
							<span className="hidden shrink-0 2xl:inline">completed {run.completedAt || "未完成"}</span>
						</div>
					}
				/>
			</Tabs>
			<BacktestOverlays
				active={activeOverlay}
				agentActions={
					<AgentContextActions
						contextType="backtest-run"
						contextId={`${run.runId}:${run.strategyId}@${run.strategyVersion}`}
						evidenceObjective="复核当前回测运行的报告、净值、基准、成交与审计证据"
					/>
				}
				onClose={() => setActiveOverlay(null)}
				onExport={exportReport}
				period={`${report?.periodStart ?? "未发布"} → ${report?.periodEnd ?? "未发布"}`}
				runId={run.runId}
				strategyIdentity={`${run.strategyId}@${run.strategyVersion}`}
			/>
		</section>
	);
}
