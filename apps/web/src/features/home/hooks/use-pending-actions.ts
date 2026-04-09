import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetPendingActionsResponse } from "@/types";

export function usePendingActions() {
	return useQuery({
		queryKey: ["home", "pending-actions"],
		queryFn: () =>
			apiClient.get<GetPendingActionsResponse>("/home/pending-actions"),
	});
}
