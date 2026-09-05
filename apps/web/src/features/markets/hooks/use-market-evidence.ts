import { useQuery } from "@tanstack/react-query";
import { fetchMacroEvidence, type MacroEvidenceRange } from "../api/market-evidence";

export const marketEvidenceKeys = {
	all: ["market-evidence"] as const,
	macro: (range: MacroEvidenceRange) => [...marketEvidenceKeys.all, "macro", range] as const,
};

export function useMacroEvidence(range: MacroEvidenceRange) {
	return useQuery({
		queryKey: marketEvidenceKeys.macro(range),
		queryFn: () => fetchMacroEvidence(range),
		enabled: range.allowExperimentalData,
	});
}
