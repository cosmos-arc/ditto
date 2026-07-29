import { createFileRoute, Outlet } from "@tanstack/react-router";
import { ResearchSubNav } from "@/features/research";

export const Route = createFileRoute("/research")({
	component: ResearchLayout,
	staticData: { title: "研究" },
});

function ResearchLayout() {
	return (
		<div className="flex h-full flex-col">
			<ResearchSubNav />
			<div className="min-h-0 flex-1">
				<Outlet />
			</div>
		</div>
	);
}
