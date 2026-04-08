import { createRootRoute, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { AppShell } from "@/features/shell";

export const Route = createRootRoute({
	component: RootLayout,
});

function RootLayout(): ReactNode {
	return (
		<AppShell>
			<Outlet />
		</AppShell>
	);
}
