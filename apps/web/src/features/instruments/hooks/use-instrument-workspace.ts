import { useQuery } from "@tanstack/react-query";
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
