import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layouts/app-shell";
import { ResearchPage } from "@/features/research";

export const Route = createFileRoute("/research")({
	component: ResearchRoute,
});

function ResearchRoute() {
	return (
		<AppShell activeNavKey="research">
			<ResearchPage />
		</AppShell>
	);
}
