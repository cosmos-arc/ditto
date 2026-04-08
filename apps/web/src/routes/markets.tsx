import { createFileRoute, Outlet } from "@tanstack/react-router";
import { AnalyticalLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/markets")({
	component: MarketsLayout,
	handle: { title: "市场" },
});

function MarketsLayout() {
	return (
		<AnalyticalLayout
			strip={<Placeholder label="Scope Strip" />}
			main={<Outlet />}
			activity={<Placeholder label="Activity Stack" />}
			analysis={<Placeholder label="Analysis Band" />}
		/>
	)
}
