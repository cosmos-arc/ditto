import { CommandCenterLayout, StatusBar } from "@/features/shell";
import { AiPulseStrip } from "./ai-pulse-strip";
import { AiMainContent } from "./ai-main-content";
import { AiContextSidebar } from "./ai-context-sidebar";

export function AiPage() {
	return (
		<>
			<CommandCenterLayout
				className="pb-(--height-status-bar)"
				pulse={<AiPulseStrip />}
				main={<AiMainContent />}
				sidebar={<AiContextSidebar />}
			/>
			<StatusBar />
		</>
	);
}
