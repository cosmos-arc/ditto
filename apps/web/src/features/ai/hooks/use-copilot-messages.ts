import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { CopilotMessage } from "@/types";

interface CopilotMessagesResponse {
	readonly messages: readonly CopilotMessage[];
}

export function useCopilotMessages(sessionId: string) {
	return useQuery({
		queryKey: ["ai", "copilot", "sessions", sessionId, "messages"],
		queryFn: () =>
			apiClient.get<CopilotMessagesResponse>(
				`/ai/copilot/sessions/${sessionId}/messages`,
			),
		enabled: sessionId.length > 0,
	});
}
