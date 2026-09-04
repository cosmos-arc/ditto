import { createFileRoute, Outlet, useLocation } from "@tanstack/react-router";
import { ResearchSubNav } from "@/features/research";

export const Route = createFileRoute("/research")({
	component: ResearchLayout,
	staticData: { title: "研究" },
});

function ResearchLayout() {
	const { pathname } = useLocation();
	const immersiveWorkspace =
		pathname === "/research" ||
		pathname === "/research/universes" ||
		pathname === "/research/agent" ||
		pathname.startsWith("/research/experiments/") ||
		pathname.startsWith("/research/factors") ||
		pathname.startsWith("/research/reviews/") ||
		pathname.startsWith("/research/backtests") ||
		pathname.startsWith("/research/strategies") ||
		pathname.endsWith("/studio");
	return (
		<div className="flex h-full flex-col">
			{!immersiveWorkspace && <ResearchSubNav />}
			<div className="min-h-0 flex-1">
				<Outlet />
			</div>
		</div>
	);
}
