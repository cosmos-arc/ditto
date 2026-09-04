import { useQuery } from "@tanstack/react-query";
import { fetchInstrumentCatalog, type InstrumentCatalogFilter } from "@/features/instruments/api/instrument-catalog";
import { fetchCurrentMarketContext, fetchMacroEvidence, type MacroEvidenceRange } from "../api/market-evidence";

export const marketEvidenceKeys = {
	all: ["market-evidence"] as const,
	catalog: (filter: InstrumentCatalogFilter) => [...marketEvidenceKeys.all, "catalog", filter] as const,
	macro: (range: MacroEvidenceRange) => [...marketEvidenceKeys.all, "macro", range] as const,
	context: (asOf?: string) => [...marketEvidenceKeys.all, "context", asOf ?? "current"] as const,
};

export function useMarketCatalog(filter: InstrumentCatalogFilter = {}) {
	return useQuery({
		queryKey: marketEvidenceKeys.catalog(filter),
		queryFn: () => fetchInstrumentCatalog(filter),
		staleTime: 60_000,
	});
}

export function useMacroEvidence(range: MacroEvidenceRange) {
	return useQuery({
		queryKey: marketEvidenceKeys.macro(range),
		queryFn: () => fetchMacroEvidence(range),
		enabled: range.allowExperimentalData,
	});
}

export function useMarketContext(asOf?: string) {
	return useQuery({
		queryKey: marketEvidenceKeys.context(asOf),
		queryFn: () => fetchCurrentMarketContext(asOf),
		staleTime: 60_000,
	});
}
