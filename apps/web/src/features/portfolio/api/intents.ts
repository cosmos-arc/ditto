import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type UpdateIntentStatusRequest = components["schemas"]["UpdateIntentStatusRequest"];
export type IntentStatus = UpdateIntentStatusRequest["status"];

export function updateIntentStatus(intentId: string, status: IntentStatus): Promise<boolean> {
	return apiClient.put<boolean>(`/v1/manual/intents/${encodeURIComponent(intentId)}/status`, {
		status,
	} satisfies UpdateIntentStatusRequest);
}
