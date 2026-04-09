import { StudioLayout } from "@/features/shell";
import { CopilotSessionList } from "./copilot-session-list";
import { CopilotChatView } from "./copilot-chat-view";

export function CopilotPage() {
	return (
		<StudioLayout
			source={<CopilotSessionList />}
			main={<CopilotChatView sessionId="session-001" />}
		/>
	);
}
