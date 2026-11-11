import { createFileRoute } from "@tanstack/react-router";
import { SelectionWorkspacePage } from "@/features/selection";

type ScreenerSearch = ReturnType<typeof validateScreenerSearch>;

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
				// 函数式 search 更新：同一次事件里可能连发 spec+run 两次导航
				// （如创建运行成功），闭包里的旧 search 会让后一次覆盖前一次。
				void navigate({
					replace: true,
					search: (prev: ScreenerSearch) => ({ ...prev, spec: specId || undefined }),
				});
			}}
			onRunIdChange={(runId) => {
				void navigate({
					replace: true,
					search: (prev: ScreenerSearch) => ({ ...prev, run: runId || undefined }),
				});
			}}
			onTabChange={(tab) => {
				void navigate({
					replace: true,
					search: (prev: ScreenerSearch) => ({
						...prev,
						tab: tab === "exclusions" ? "exclusions" : undefined,
					}),
				});
			}}
		/>
	);
}
