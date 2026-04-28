import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type { GetInstrumentChartResponse } from "@/types";

type ChartParams = {
	readonly period?: string;
	readonly interval?: string;
};

export function useInstrumentChart(id: string, params?: ChartParams) {
	return useQuery({
		queryKey: ["instruments", id, "chart", params],
		queryFn: () =>
			apiClient.get<GetInstrumentChartResponse>(
				withQueryParams(`/instruments/${id}/chart`, params),
			),
		enabled: id.length > 0,
	});
}
