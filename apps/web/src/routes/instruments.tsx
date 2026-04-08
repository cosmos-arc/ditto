import { createFileRoute, Outlet } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/instruments")({
	component: InstrumentsLayout,
	handle: { title: "标的详情" },
});

function InstrumentsLayout() {
	return (
		<ObjectHubLayout
			meta={<Placeholder label="Object Meta" />}
			tabs={<Placeholder label="Tab Bar" />}
			main={<Outlet />}
			bottom={<Placeholder label="Bottom" />}
		/>
	)
}
