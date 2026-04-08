import { createFileRoute, Outlet } from "@tanstack/react-router";
import { StudioLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/ai")({
	component: AILayout,
	handle: { title: "AI" },
});

function AILayout() {
	return (
		<StudioLayout
			source={<Placeholder label="Sessions Panel" />}
			main={<Outlet />}
			inspector={<Placeholder label="Context Panel" />}
			logs={<Placeholder label="Logs" />}
		/>
	)
}
