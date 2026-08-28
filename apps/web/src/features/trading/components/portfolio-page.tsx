import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { AnalyticalLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useComparisonAttribution, useDailyDecisionV3 } from "../hooks";
import { FillLedgerList } from "./fill-ledger-list";
import { PortfolioConstructionEvidence } from "./portfolio-construction-evidence";
import { PositionsSummary } from "./positions-summary";
import { SignalToOrderPipelineStrip } from "./signal-to-order-pipeline-strip";

const PORTFOLIO_ROWS = [
	["权益", "68.2%", "+1.4%"],
	["债券", "18.5%", "+0.2%"],
	["现金", "13.3%", "0.0%"],
] as const;

interface PortfolioPageProps {
	readonly comparisonRunId?: string;
}

function AttributionPanel({ comparisonRunId }: PortfolioPageProps) {
	const hasRunId = Boolean(comparisonRunId);
	const { data, isLoading } = useComparisonAttribution({ runId: comparisonRunId ?? "" }, { enabled: hasRunId });

	if (!hasRunId) {
		return (
			<Panel>
				<PanelHeader title="归因" />
				<PanelBody className="p-(--density-panel-padding)">
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)">
						无归因数据
					</div>
				</PanelBody>
			</Panel>
		);
	}

	return (
		<Panel>
			<PanelHeader title="回测 vs 实盘归因" count={data?.rows.length} />
			<PanelBody className="p-(--density-panel-padding)">
				{isLoading && <LoadingSkeleton variant="table" rows={4} />}
				{data && (
					<div className="flex flex-col gap-1">
						{data.rows.map((row) => (
							<div
								key={row.label}
								className="grid grid-cols-[7rem_5rem_1fr] items-center gap-2 rounded-(--radius-sm) px-2 py-2 text-sm hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span className="text-(--color-foreground-secondary)">{row.label}</span>
								<span className="font-data tabular-nums text-(--color-foreground)">{row.value}</span>
								<span className="truncate text-xs text-(--color-foreground-tertiary)">{row.detail}</span>
							</div>
						))}
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}

export function PortfolioPage({ comparisonRunId }: PortfolioPageProps = {}) {
	const liveMode = !shouldUsePrototypeMocks();
	const {
		data: dailyDecision,
		isLoading,
		isError,
		refetch,
	} = useDailyDecisionV3(undefined, {
		enabled: liveMode,
	});

	if (liveMode) {
		return (
			<>
				<AnalyticalLayout
					className="pb-(--height-status-bar)"
					strip={
						<div className="flex flex-col">
							<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2">
								<p className="text-sm font-medium text-(--color-foreground)">组合总览</p>
								<span className="font-data text-xs text-(--color-foreground-tertiary)">Daily Decision V3</span>
							</div>
							<SignalToOrderPipelineStrip />
						</div>
					}
					main={
						<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
							{isError && (
								<div
									role="alert"
									className="flex items-center justify-between rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-2 text-sm"
								>
									<span>组合实盘数据加载失败，未使用原型数据替代。</span>
									<Button variant="outline" size="sm" onClick={() => void refetch()}>
										重试
									</Button>
								</div>
							)}
							{isLoading && <LoadingSkeleton variant="panel" rows={5} />}
							{!isLoading && !isError && !dailyDecision && (
								<div role="status" className="rounded-(--radius-sm) border border-(--color-border-subtle) p-4 text-sm">
									暂无组合构建决策
								</div>
							)}
							{dailyDecision && <PortfolioConstructionEvidence decision={dailyDecision} />}
							<PositionsSummary />
						</div>
					}
					activity={
						<div className="m-4 ml-0 flex min-h-0 flex-col gap-(--section-gap)">
							<AttributionPanel comparisonRunId={comparisonRunId} />
							<FillLedgerList />
						</div>
					}
					analysis={
						<div className="border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2 text-xs text-(--color-foreground-tertiary)">
							comparison 需要回测 run_id；未提供时保持结构化空态。
						</div>
					}
				/>
				<StatusBar />
			</>
		);
	}

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={
					<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<p className="text-sm font-medium text-(--color-foreground)">组合总览</p>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">T+0 exposure</span>
					</div>
				}
				main={
					<Panel className="m-4">
						<PanelHeader title="Allocation" />
						<PanelBody>
							<div className="divide-y divide-(--color-border-subtle)">
								{PORTFOLIO_ROWS.map(([asset, weight, pnl]) => (
									<div key={asset} className="grid grid-cols-[1fr_5rem_5rem] items-center px-3 py-2 text-sm">
										<span className="text-(--color-foreground)">{asset}</span>
										<span className="font-data text-(--color-foreground-tertiary)">{weight}</span>
										<span className="font-data text-(--color-market-up-fg)">{pnl}</span>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
				}
				activity={
					<Panel className="m-4 ml-0">
						<PanelHeader title="Activity" />
						<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
							最近调仓、资金流和执行偏离。
						</PanelBody>
					</Panel>
				}
				analysis={
					<div className="border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2 text-xs text-(--color-foreground-tertiary)">
						风险预算、回撤贡献和行业偏离在此汇总。
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
