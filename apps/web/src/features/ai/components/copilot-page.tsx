import { StudioLayout, StatusBar } from "@/features/shell";
import { CopilotSessionList } from "./copilot-session-list";
import { CopilotChatView } from "./copilot-chat-view";
import { CopilotContextPanel } from "./copilot-context-panel";

export function CopilotPage() {
	return (
		<>
			<StudioLayout
				className="pb-(--height-status-bar)"
				source={
					<div data-info-level="l1" data-info-unit="copilot-session-list">
						<CopilotSessionList />
					</div>
				}
				main={
					<div data-info-level="l1" data-info-unit="copilot-chat">
						<CopilotChatView sessionId="session-001" />
					</div>
				}
				inspector={
					<div data-info-level="l2" data-info-unit="copilot-context-panel">
						<CopilotContextPanel />
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
