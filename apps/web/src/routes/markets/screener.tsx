import { createFileRoute } from "@tanstack/react-router";
import { SelectionWorkspacePage } from "@/features/selection";

/** 运行历史范围随 URL 携带：刷新或返回后恢复到同一筛选条件身份。 */
const validateScreenerSearch = (search: Record<string, unknown>) => {
	const spec = search["spec"];
	return { spec: typeof spec === "string" && spec.trim() ? spec : undefined };
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
			onSpecIdChange={(specId) => {
				void navigate({ replace: true, search: { spec: specId || undefined } });
			}}
		/>
	);
}
