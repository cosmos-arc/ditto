import { createFileRoute } from "@tanstack/react-router";
import { CommandCenterLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/")({
	component: HomePage,
	handle: { title: "首页" },
});

function HomePage() {
	return (
		<CommandCenterLayout
			pulse={<Placeholder label="Pulse Strip" />}
			main={<Placeholder label="Main Content" />}
			sidebar={<Placeholder label="Sidebar" />}
		/>
	);
}
