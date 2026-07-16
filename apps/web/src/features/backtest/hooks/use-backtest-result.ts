import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetBacktestResultResponse } from "@/types";

export function useBacktestResult(jobId: string) {
	return useQuery({
		queryKey: ["backtest", jobId],
		queryFn: () =>
			apiClient.get<GetBacktestResultResponse>(`/research/backtest/${jobId}`),
	});
}
