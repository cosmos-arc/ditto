import { createFileRoute, Outlet } from "@tanstack/react-router";
import { AnalyticalLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/trading")({
	component: TradingLayout,
	handle: { title: "交易" },
});

function TradingLayout() {
	return (
		<AnalyticalLayout
			strip={<Placeholder label="Scope Strip" />}
			main={<Outlet />}
			activity={<Placeholder label="Activity Stack" />}
			analysis={<Placeholder label="Analysis Band" />}
		/>
	)
}
