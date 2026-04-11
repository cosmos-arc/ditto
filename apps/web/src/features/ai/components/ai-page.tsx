import { CommandCenterLayout, StatusBar } from "@/features/shell";
import { AiPulseStrip } from "./ai-pulse-strip";
import { AgentQuickView } from "./agent-quick-view";
import { CopilotQuickView } from "./copilot-quick-view";

export function AiPage() {
	return (
		<CommandCenterLayout
			pulse={<AiPulseStrip />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<AgentQuickView />
					<CopilotQuickView />
				</div>
			}
			status={<StatusBar />}
		/>
	);
}
