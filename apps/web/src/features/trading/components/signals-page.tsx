import { OpsConsoleLayout } from "@/features/shell";
import { SignalsList } from "./signals-list";
import { SignalsHealthStrip } from "./signals-health-strip";
import { SignalDetailPanel } from "./signal-detail-panel";

const DEFAULT_SIGNAL_ID = "sig-001";

export function SignalsPage() {
	return (
		<OpsConsoleLayout
			health={<SignalsHealthStrip />}
			main={<SignalsList />}
			detail={
				<div className="h-full overflow-y-auto">
					<SignalDetailPanel signalId={DEFAULT_SIGNAL_ID} />
				</div>
			}
		/>
	);
}
