import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type IntentStatus, updateIntentStatus } from "../api/intents";
import { tradingKeys } from "../api/query-keys";

const UPDATE_INTENT_INVALIDATION_SCOPES = ["daily-decision", "signals", "deviation"] as const;

interface UpdateIntentStatusVariables {
	readonly intentId: string;
	readonly status: IntentStatus;
}

export function useUpdateIntentStatus() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: ({ intentId, status }: UpdateIntentStatusVariables) => updateIntentStatus(intentId, status),
		onSuccess: () => {
			for (const scope of UPDATE_INTENT_INVALIDATION_SCOPES) {
				void queryClient.invalidateQueries({ queryKey: [...tradingKeys.all, scope] });
			}
		},
	});
}
