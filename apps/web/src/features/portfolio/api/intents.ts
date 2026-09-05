import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export type UpdateIntentStatusRequest = components["schemas"]["UpdateIntentStatusRequest"];
export type IntentStatus = UpdateIntentStatusRequest["status"];

export function updateIntentStatus(intentId: string, status: IntentStatus): Promise<boolean> {
	return apiClient.put("/api/v1/manual/intents/{intent_id}/status", {
		body: { status } satisfies UpdateIntentStatusRequest,
		params: { path: { intent_id: intentId } },
	});
}
