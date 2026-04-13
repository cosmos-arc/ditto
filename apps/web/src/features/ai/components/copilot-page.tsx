import { StudioLayout, StatusBar } from "@/features/shell";
import { CopilotSessionList } from "./copilot-session-list";
import { CopilotChatView } from "./copilot-chat-view";
import { CopilotContextPanel } from "./copilot-context-panel";

export function CopilotPage() {
	return (
		<>
			<StudioLayout
				className="pb-(--height-status-bar)"
				style={{ "--width-studio-source": "220px", "--width-studio-inspector": "280px" }}
				source={<CopilotSessionList />}
				main={<CopilotChatView sessionId="session-001" />}
				inspector={<CopilotContextPanel />}
			/>
			<StatusBar />
		</>
	);
}
