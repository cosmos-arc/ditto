import { useState } from "react";
import {
	OpsConsoleLayout,
	OverlayProvider,
	StatusBar,
	useOverlayController,
} from "@/features/shell";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { SignalsList } from "./signals-list";
import { SignalsHealthStrip } from "./signals-health-strip";
import { SignalDetailPanel } from "./signal-detail-panel";

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
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();

	function handleSelectSignal(signalId: string) {
		setSelectedSignalId(signalId);
		openOverlay(SIGNAL_DETAIL_OVERLAY_ID);
	}

	function handleCloseSignalDetail() {
		closeOverlay();
		setSelectedSignalId(null);
	}

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={<SignalsHealthStrip />}
				main={<SignalsList onSelectSignal={handleSelectSignal} />}
			/>
			<StatusBar />
			<Drawer
				open={activeOverlayId === SIGNAL_DETAIL_OVERLAY_ID && selectedSignalId !== null}
				onClose={handleCloseSignalDetail}
				title="信号详情"
			>
				<div className="h-full overflow-y-auto" data-info-level="l3" data-info-unit="signal-detail">
					{selectedSignalId && <SignalDetailPanel signalId={selectedSignalId} />}
				</div>
			</Drawer>
		</>
	);
}
