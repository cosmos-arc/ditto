import { createFileRoute, Outlet } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/strategies")({
	component: StrategiesLayout,
	handle: { title: "策略详情" },
});

function StrategiesLayout() {
	return (
		<ObjectHubLayout
			meta={<Placeholder label="Strategy Meta" />}
			tabs={<Placeholder label="Tab Bar" />}
			main={<Outlet />}
			bottom={<Placeholder label="Bottom" />}
		/>
	)
}
