import { createFileRoute } from "@tanstack/react-router";
import { InstrumentHubPage, type InstrumentHubSearch } from "@/workflows/instrument-analysis";

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

export function parseInstrumentSearch(search: Record<string, unknown>): InstrumentHubSearch {
	const tab = search["tab"];
	const direction = optionalString(search["drillDirection"]);
	// 观察日锚点（跨域跳转合同）：自选/筛选带入的最近完整交易日，严格 ISO 日期。
	const rawObserveDate = optionalString(search["observeDate"]);
	const observeDate =
		rawObserveDate !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(rawObserveDate) ? rawObserveDate : undefined;
	return {
		selectionRunId: optionalString(search["selectionRunId"]),
		tab: tab === "capital" || tab === "chart" || tab === "fundamentals" || tab === "technical" ? tab : "overview",
		// 回测买卖点下钻上下文（跨域跳转合同）：对象=focusDate 标的、原因=runId、知识时间=drillAsOf。
		drill:
			optionalString(search["focusDate"]) !== undefined
				? {
						date: optionalString(search["focusDate"]) ?? "",
						runId: optionalString(search["drillRunId"]) ?? "",
						asOf: optionalString(search["drillAsOf"]) ?? "",
						direction: direction === "sell" ? "sell" : "buy",
					}
				: undefined,
		observeDate,
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
