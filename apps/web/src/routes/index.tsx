import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layouts/app-shell";
import { DashboardShell } from "@/features/dashboard/components/dashboard-shell";

export const Route = createFileRoute("/")({
	component: IndexPage,
});

function IndexPage() {
	return (
		<AppShell activeNavKey="dashboard">
			<DashboardShell />
		</AppShell>
	);
}
