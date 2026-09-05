import { useParams } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ObjectHubLayout, StatusBar } from "@/features/shell";
import { addToLocalWatchlist } from "@/lib/local-watchlist";
import { InstrumentChartView } from "./instrument-chart-view";
import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";
import { type InstrumentOverlayId, InstrumentPageOverlays, instrumentActions } from "./instrument-page-overlays";

export interface InstrumentHubSearch {
	readonly selectionRunId?: string | undefined;
	readonly tab?: "chart" | "fundamentals" | "overview" | "technical";
}

export interface InstrumentTechnicalSlotProps {
	readonly id: string;
	readonly onSnapshotIdentity?: (snapshotId: string | null) => void;
	readonly selectionRunId: string | undefined;
}

export function InstrumentHubPage({
	renderTechnical,
	search = {},
}: {
	readonly renderTechnical?: (props: InstrumentTechnicalSlotProps) => ReactNode;
	readonly search?: InstrumentHubSearch;
}) {
	const { id } = useParams({ strict: false }) as { id: string };
	const instrumentId = id ?? "";
	const [activeOverlay, setActiveOverlay] = useState<InstrumentOverlayId | null>(null);
	const [feedback, setFeedback] = useState<string | null>(null);
	const [technicalSnapshotId, setTechnicalSnapshotId] = useState<string | null>(null);

	function addWatchlist(): void {
		const numericId = Number(instrumentId);
		if (!Number.isInteger(numericId) || numericId <= 0) {
			setFeedback("标的 identity 无效，未写入本机自选");
		} else {
			addToLocalWatchlist(numericId);
			setFeedback(`Instrument ${instrumentId} 已加入本机自选`);
		}
		setActiveOverlay(null);
	}

	return (
		<>
			<Tabs defaultValue={search.tab ?? "overview"} className="h-full">
				<ObjectHubLayout
					className="pb-(--height-status-bar)"
					meta={
						<div data-info-level="l1" data-info-unit="instrument-meta">
							<InstrumentMetaStrip id={instrumentId} />
						</div>
					}
					tabs={
						<div
							className="flex h-11 items-center border-b border-(--color-border-subtle) px-3"
							data-info-level="l1"
							data-info-unit="instrument-tabs"
						>
							<TabsList>
								<TabsTrigger value="overview">概览</TabsTrigger>
								<TabsTrigger value="chart">行情</TabsTrigger>
								<TabsTrigger value="technical">技术证据</TabsTrigger>
								<TabsTrigger value="fundamentals">数据边界</TabsTrigger>
							</TabsList>
						</div>
					}
					main={
						<>
							<TabsContent value="overview">
								<div data-info-level="l1" data-info-unit="instrument-overview">
									<InstrumentOverview id={instrumentId} />
								</div>
							</TabsContent>
							<TabsContent value="chart">
								<div data-info-level="l1" data-info-unit="instrument-chart">
									<InstrumentChartView id={instrumentId} />
								</div>
							</TabsContent>
							<TabsContent value="technical" className="h-full min-h-0 overflow-hidden">
								<div data-info-level="l1" data-info-unit="instrument-technical" className="h-full">
									{renderTechnical ? (
										renderTechnical({
											id: instrumentId,
											onSnapshotIdentity: setTechnicalSnapshotId,
											selectionRunId: search.selectionRunId,
										})
									) : (
										<p className="p-6 text-sm text-(--color-foreground-tertiary)">
											技术证据需要由 app workflow 注入精确 SelectionRun 与 Data Product evidence。
										</p>
									)}
								</div>
							</TabsContent>
							<TabsContent value="fundamentals">
								<div data-info-level="l1" data-info-unit="instrument-fundamentals">
									<InstrumentOverview id={instrumentId} />
								</div>
							</TabsContent>
						</>
					}
					bottom={
						<div className="flex h-9 items-center gap-3 overflow-hidden border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3">
							<span className="min-w-0 flex-1 truncate text-xs text-(--color-foreground-tertiary)">
								{feedback ??
									"公开合同：metadata identity + exact date-range bars · 缺少 snapshot identity 时不用于交易决策"}
							</span>
							<PageActionBar ariaLabel="标的页面操作" actions={instrumentActions} onOpen={setActiveOverlay} />
						</div>
					}
				/>
			</Tabs>
			<StatusBar />
			<InstrumentPageOverlays
				active={activeOverlay}
				instrumentId={instrumentId}
				onAddWatchlist={addWatchlist}
				onClose={() => setActiveOverlay(null)}
				selectionRunId={search.selectionRunId}
				technicalSnapshotId={technicalSnapshotId}
			/>
		</>
	);
}
