import { createFileRoute } from "@tanstack/react-router";
import { InstrumentHubPage, type InstrumentHubSearch } from "@/features/instruments";

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

export function parseInstrumentSearch(search: Record<string, unknown>): InstrumentHubSearch {
	const tab = search.tab;
	return {
		selectionRunId: optionalString(search.selectionRunId),
		tab: tab === "chart" || tab === "fundamentals" || tab === "technical" ? tab : "overview",
	};
}

function InstrumentRoute() {
	return <InstrumentHubPage search={Route.useSearch()} />;
}

export const Route = createFileRoute("/instruments/$id")({
	validateSearch: parseInstrumentSearch,
	component: InstrumentRoute,
	staticData: { title: "标的详情" },
});
