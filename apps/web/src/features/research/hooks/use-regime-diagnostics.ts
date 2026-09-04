import { useQuery } from "@tanstack/react-query";
import { fetchRegimeDiagnostics, type RegimeDiagnosticsScope } from "../api/regime-diagnostics";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u;
const SHA_256 = /^[0-9a-f]{64}$/u;

export function isCompleteRegimeScope(scope: RegimeDiagnosticsScope | null): scope is RegimeDiagnosticsScope {
	return Boolean(
		scope &&
			scope.snapshotId.trim() === scope.snapshotId &&
			scope.snapshotId.length > 0 &&
			SHA_256.test(scope.snapshotManifestHash) &&
			Number.isInteger(scope.benchmarkInstrumentId) &&
			scope.benchmarkInstrumentId > 0 &&
			ISO_DATE.test(scope.startDate) &&
			ISO_DATE.test(scope.endDate) &&
			ISO_DATE.test(scope.knowledgeCutoff) &&
			scope.startDate <= scope.endDate &&
			scope.endDate < scope.knowledgeCutoff,
	);
}

export const regimeDiagnosticsKeys = {
	all: ["research", "regime", "diagnostics"] as const,
	detail: (scope: RegimeDiagnosticsScope | null) =>
		[
			...regimeDiagnosticsKeys.all,
			scope?.snapshotId ?? "",
			scope?.snapshotManifestHash ?? "",
			scope?.benchmarkInstrumentId ?? 0,
			scope?.startDate ?? "",
			scope?.endDate ?? "",
			scope?.knowledgeCutoff ?? "",
		] as const,
};

export function useRegimeDiagnostics(scope: RegimeDiagnosticsScope | null) {
	return useQuery({
		queryKey: regimeDiagnosticsKeys.detail(scope),
		queryFn: () => {
			if (!isCompleteRegimeScope(scope)) throw new Error("Regime diagnostics require an exact PIT scope");
			return fetchRegimeDiagnostics(scope);
		},
		enabled: isCompleteRegimeScope(scope),
		staleTime: 60_000,
	});
}
