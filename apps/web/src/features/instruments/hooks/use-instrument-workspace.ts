import { useQuery } from "@tanstack/react-query";
import { fetchEtfNav, fetchIndicatorSeries, type IndicatorSeriesRange } from "../api/indicator-overlays";
import {
	fetchInstrumentBars,
	fetchInstrumentIdentity,
	type InstrumentBarRange,
	parseInstrumentId,
} from "../api/instrument-workspace";

function hasValidId(id: string): boolean {
	try {
		parseInstrumentId(id);
		return true;
	} catch {
		return false;
	}
}

export const instrumentKeys = {
	all: ["instruments"] as const,
	bars: (id: string, range: InstrumentBarRange) => [...instrumentKeys.all, id, "bars", range] as const,
	detail: (id: string) => [...instrumentKeys.all, id, "identity"] as const,
	indicators: (id: string, range: IndicatorSeriesRange) =>
		[...instrumentKeys.all, id, "indicator-series", range] as const,
	nav: (id: string, range: { readonly startDate: string; readonly endDate: string }) =>
		[...instrumentKeys.all, id, "etf-nav", range] as const,
};

export function useInstrumentDetail(id: string) {
	return useQuery({
		queryKey: instrumentKeys.detail(id),
		queryFn: () => fetchInstrumentIdentity(id),
		enabled: hasValidId(id),
	});
}

export function useInstrumentChart(id: string, range: InstrumentBarRange) {
	return useQuery({
		queryKey: instrumentKeys.bars(id, range),
		queryFn: () => fetchInstrumentBars(id, range),
		enabled: hasValidId(id) && range.startDate.length > 0 && range.endDate.length > 0,
	});
}

export function useIndicatorSeries(id: string, range: IndicatorSeriesRange) {
	return useQuery({
		queryKey: instrumentKeys.indicators(id, range),
		queryFn: () => fetchIndicatorSeries(id, range),
		enabled: hasValidId(id) && range.indicators.length > 0 && range.startDate.length > 0,
	});
}

export function useEtfNav(id: string, range: { readonly startDate: string; readonly endDate: string }) {
	return useQuery({
		queryKey: instrumentKeys.nav(id, range),
		queryFn: () => fetchEtfNav(id, range),
		enabled: hasValidId(id) && range.startDate.length > 0 && range.endDate.length > 0,
	});
}
