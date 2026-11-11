import { createFileRoute } from "@tanstack/react-router";
import { SelectionWorkspacePage } from "@/features/selection";

/** 运行历史范围与固定运行随 URL 携带：刷新或返回后恢复到同一证据上下文。 */
const validateScreenerSearch = (search: Record<string, unknown>) => {
	const spec = search["spec"];
	const run = search["run"];
	const tab = search["tab"];
	return {
		spec: typeof spec === "string" && spec.trim() ? spec : undefined,
		run: typeof run === "string" && run.trim() ? run : undefined,
		tab: tab === "exclusions" ? ("exclusions" as const) : undefined,
	};
};

export const Route = createFileRoute("/markets/screener")({
	validateSearch: validateScreenerSearch,
	component: ScreenerRoute,
	staticData: { title: "Selection Workspace" },
});

function ScreenerRoute() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();
	return (
		<SelectionWorkspacePage
			initialSpecId={search.spec}
			initialRunId={search.run}
			initialTab={search.tab}
			onSpecIdChange={(specId) => {
				void navigate({ replace: true, search: { ...search, spec: specId || undefined } });
			}}
			onRunIdChange={(runId) => {
				void navigate({ replace: true, search: { ...search, run: runId || undefined } });
			}}
			onTabChange={(tab) => {
				void navigate({
					replace: true,
					search: { ...search, tab: tab === "exclusions" ? "exclusions" : undefined },
				});
			}}
		/>
	);
}
