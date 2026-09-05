import { createFileRoute } from "@tanstack/react-router";
import { type FactorDiagnosticsScope, FactorPage } from "@/features/research";

interface FactorDiagnosticsSearch {
	readonly snapshotId: string;
	readonly startDate: string;
	readonly endDate: string;
	readonly registryHash: string;
}

function parseDiagnosticsSearch(search: Record<string, unknown>): FactorDiagnosticsSearch {
	return {
		snapshotId: typeof search["snapshotId"] === "string" ? search["snapshotId"] : "",
		startDate: typeof search["startDate"] === "string" ? search["startDate"] : "",
		endDate: typeof search["endDate"] === "string" ? search["endDate"] : "",
		registryHash: typeof search["registryHash"] === "string" ? search["registryHash"] : "",
	};
}

function FactorDiagnosticsRoute() {
	const search = Route.useSearch();
	const scope: FactorDiagnosticsScope | null =
		search.snapshotId && search.startDate && search.endDate && search.registryHash ? search : null;
	return <FactorPage initialScope={scope} />;
}

export const Route = createFileRoute("/research/factors/$id")({
	validateSearch: parseDiagnosticsSearch,
	component: FactorDiagnosticsRoute,
	staticData: { title: "因子分析" },
});
