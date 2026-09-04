import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { AnalyticalLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { PortfolioComparisonIdentity } from "../api/portfolio-comparison";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useComparisonAttribution, useDailyDecisionV3 } from "../hooks";
import { AccountIdentityStrip } from "./account-identity-strip";
import { FillLedgerList } from "./fill-ledger-list";
import { ManualAccountWorkspace } from "./manual-account-workspace";
import { PaperAccountWorkspace } from "./paper-account-workspace";
import { PortfolioComparisonWorkspace } from "./portfolio-comparison-workspace";
import { PortfolioConstructionEvidence } from "./portfolio-construction-evidence";
import { PortfolioMockWorkspace } from "./portfolio-workspace";
import { PositionsSummary } from "./positions-summary";
import { SignalToOrderPipelineStrip } from "./signal-to-order-pipeline-strip";

interface PortfolioPageProps {
	readonly comparisonRunId?: string;
	readonly mode?: PortfolioMode;
}

export type PortfolioMode = "comparison" | "manual" | "model" | "paper";

function readComparisonIdentity(search: URLSearchParams): PortfolioComparisonIdentity | undefined {
	const required = {
		strategy_id: search.get("strategy_id"),
		model_portfolio_id: search.get("model_portfolio_id"),
		paper_account_id: search.get("paper_account_id"),
		manual_account_id: search.get("manual_account_id"),
		paper_session_id: search.get("paper_session_id"),
		as_of: search.get("as_of"),
		knowledge_cutoff: search.get("knowledge_cutoff"),
		publication_cutoff: search.get("publication_cutoff"),
	};
	if (Object.values(required).some((value) => !value || value.trim() !== value)) return undefined;
	const sourceSnapshotIds = search.getAll("source_snapshot_ids").filter((value) => value && value.trim() === value);
	if (sourceSnapshotIds.length === 0 || new Set(sourceSnapshotIds).size !== sourceSnapshotIds.length) return undefined;
	const valuationSnapshotId = search.get("valuation_snapshot_id");
	return {
		strategy_id: required.strategy_id as string,
		model_portfolio_id: required.model_portfolio_id as string,
		paper_account_id: required.paper_account_id as string,
		manual_account_id: required.manual_account_id as string,
		paper_session_id: required.paper_session_id as string,
		as_of: required.as_of as string,
		knowledge_cutoff: required.knowledge_cutoff as string,
		publication_cutoff: required.publication_cutoff as string,
		source_snapshot_ids: sourceSnapshotIds,
		...(valuationSnapshotId ? { valuation_snapshot_id: valuationSnapshotId } : {}),
	};
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
			<PanelHeader title="回测 vs Manual 归因" count={data?.rows.length} />
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

export function PortfolioPage({ comparisonRunId, mode }: PortfolioPageProps = {}) {
	const liveMode = !shouldUsePrototypeMocks();
	const search = new URLSearchParams(window.location.search);
	const requestedMode = mode ?? search.get("mode");
	const accountMode =
		requestedMode === "comparison"
			? "comparison"
			: requestedMode === "paper"
				? "paper"
				: requestedMode === "manual"
					? "manual"
					: "model";
	const comparisonIdentity = accountMode === "comparison" ? readComparisonIdentity(search) : undefined;
	const [manualAccountId, setManualAccountId] = useState(() =>
		accountMode === "manual" ? (search.get("account_id") ?? undefined) : undefined,
	);
	const [paperWorkspace, setPaperWorkspace] = useState(() => ({
		accountId: accountMode === "paper" ? (search.get("account_id") ?? undefined) : undefined,
		sessionId: accountMode === "paper" ? (search.get("session_id") ?? undefined) : undefined,
	}));
	const {
		data: dailyDecision,
		isLoading,
		isError,
		refetch,
	} = useDailyDecisionV3(undefined, {
		enabled: liveMode && accountMode === "model",
	});

	if (liveMode && accountMode === "comparison") {
		return <PortfolioComparisonWorkspace identity={comparisonIdentity} />;
	}

	if (accountMode === "manual") {
		return (
			<ManualAccountWorkspace
				accountId={manualAccountId}
				onAccountSelected={(accountId) => {
					const next = new URL(window.location.href);
					next.searchParams.set("mode", "manual");
					next.searchParams.set("account_id", accountId);
					window.history.replaceState(window.history.state, "", next);
					setManualAccountId(accountId);
				}}
			/>
		);
	}

	if (liveMode && accountMode === "paper") {
		return (
			<PaperAccountWorkspace
				accountId={paperWorkspace.accountId}
				sessionId={paperWorkspace.sessionId}
				onWorkspaceSelected={(accountId, sessionId) => {
					const next = new URL(window.location.href);
					next.searchParams.set("mode", "paper");
					next.searchParams.set("account_id", accountId);
					next.searchParams.set("session_id", sessionId);
					window.history.replaceState(window.history.state, "", next);
					setPaperWorkspace({ accountId, sessionId });
				}}
			/>
		);
	}

	if (liveMode) {
		return (
			<AnalyticalLayout
				className="[--height-analysis-band:220px] [--width-activity:284px]"
				strip={
					<div className="flex flex-col">
						<AccountIdentityStrip kind="model" />
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
								<span>组合 Manual 数据加载失败，未使用原型数据替代。</span>
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
		);
	}

	return <PortfolioMockWorkspace />;
}
