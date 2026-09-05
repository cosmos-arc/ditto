import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { Button } from "@/components/ui/button";
import { OpsConsoleLayout, OverlayProvider, StatusBar, useOverlayController } from "@/features/shell";
import { useSignals } from "../hooks";
import { SignalDetailPanel } from "./signal-detail-panel";
import { SignalsBatchReviewDialog } from "./signals-batch-review-dialog";
import { SignalsHealthStrip } from "./signals-health-strip";
import { SignalsList } from "./signals-list";

const SIGNAL_DETAIL_OVERLAY_ID = "signals.detail";

export function SignalsPage() {
	return (
		<OverlayProvider>
			<SignalsPageContent />
		</OverlayProvider>
	);
}

function SignalsPageContent() {
	const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
	const [batchReviewOpen, setBatchReviewOpen] = useState(false);
	const signals = useSignals({ tab: "pending" });
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();
	const effectiveSignalId = selectedSignalId ?? signals.data?.items[0]?.id ?? null;

	function handleSelectSignal(signalId: string) {
		setSelectedSignalId(signalId);
		if (globalThis.matchMedia?.("(max-width: 899px)").matches ?? true) {
			openOverlay(SIGNAL_DETAIL_OVERLAY_ID);
		}
	}

	function handleCloseSignalDetail() {
		closeOverlay();
		setSelectedSignalId(null);
	}

	function startBatchReview() {
		setBatchReviewOpen(false);
		const firstSignalId = signals.data?.items[0]?.id;
		if (firstSignalId) handleSelectSignal(firstSignalId);
	}

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar) [--width-ops-detail:var(--width-signals-detail)]"
				health={<SignalsHealthStrip />}
				main={
					<div className="relative h-full">
						<SignalsList onSelectSignal={handleSelectSignal} />
						<Button
							type="button"
							variant="outline"
							size="xs"
							className="absolute top-1 right-11 z-10 max-[1279px]:top-auto max-[1279px]:right-[114px] max-[1279px]:bottom-[9px] max-[1279px]:border-(--color-accent) max-[1279px]:text-[12px] max-[1279px]:text-(--color-accent)"
							onClick={() => setBatchReviewOpen(true)}
						>
							批量复核
						</Button>
					</div>
				}
				detail={
					<div
						className="h-full overflow-y-auto border-l border-(--color-border-subtle)"
						data-info-level="l3"
						data-info-unit="signal-detail"
					>
						{effectiveSignalId ? (
							<SignalDetailPanel signalId={effectiveSignalId} />
						) : (
							<p className="p-(--density-panel-padding) text-sm text-(--color-foreground-tertiary)">
								当前没有可复核信号
							</p>
						)}
					</div>
				}
			/>
			<StatusBar spanRail />
			<SignalsBatchReviewDialog
				open={batchReviewOpen}
				onOpenChange={setBatchReviewOpen}
				pendingCount={signals.data?.total ?? 0}
				onStartReview={startBatchReview}
			/>
			<Drawer
				open={activeOverlayId === SIGNAL_DETAIL_OVERLAY_ID && effectiveSignalId !== null}
				onClose={handleCloseSignalDetail}
				title="信号详情"
			>
				<div className="h-full overflow-y-auto" data-info-level="l3" data-info-unit="signal-detail">
					{effectiveSignalId && <SignalDetailPanel signalId={effectiveSignalId} />}
				</div>
			</Drawer>
		</>
	);
}
