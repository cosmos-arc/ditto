import { createFileRoute, Outlet } from "@tanstack/react-router";
import { AnalyticalLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/research")({
	component: ResearchLayout,
	handle: { title: "研究" },
});

function ResearchLayout() {
	return (
		<AnalyticalLayout
			strip={<Placeholder label="Tab Bar" />}
			main={<Outlet />}
			activity={<Placeholder label="Secondary" />}
			analysis={<Placeholder label="Findings" />}
		/>
	)
}
