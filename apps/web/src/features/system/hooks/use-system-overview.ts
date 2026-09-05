import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
	fetchSystemCatalogAssets,
	fetchSystemFallback,
	fetchSystemPromotion,
	fetchSystemRemediation,
	fetchSystemSourceHealth,
	systemOverviewKeys,
} from "../api/system-overview";

const PLATFORM_OVERVIEW_STALE_TIME_MS = 30_000;

export function useSystemOverview(tradeDate: string) {
	const assets = useQuery({
		queryKey: systemOverviewKeys.assets(),
		queryFn: fetchSystemCatalogAssets,
		staleTime: PLATFORM_OVERVIEW_STALE_TIME_MS,
	});
	const datasetIds = useMemo(
		() => [...new Set((assets.data ?? []).map((asset) => asset.datasetId))].sort(),
		[assets.data],
	);
	const scope = useMemo(() => ({ datasetIds, tradeDate }), [datasetIds, tradeDate]);
	const enabled = datasetIds.length > 0 && tradeDate.length > 0;

	return {
		assets,
		datasetIds,
		fallback: useQuery({
			queryKey: systemOverviewKeys.fallback(scope),
			queryFn: () => fetchSystemFallback(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: PLATFORM_OVERVIEW_STALE_TIME_MS,
		}),
		promotion: useQuery({
			queryKey: systemOverviewKeys.promotion(scope),
			queryFn: () => fetchSystemPromotion(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: PLATFORM_OVERVIEW_STALE_TIME_MS,
		}),
		remediation: useQuery({
			queryKey: systemOverviewKeys.remediation(scope),
			queryFn: () => fetchSystemRemediation(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: PLATFORM_OVERVIEW_STALE_TIME_MS,
		}),
		sourceHealth: useQuery({
			queryKey: systemOverviewKeys.sourceHealth(scope),
			queryFn: () => fetchSystemSourceHealth(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: PLATFORM_OVERVIEW_STALE_TIME_MS,
		}),
	};
}
