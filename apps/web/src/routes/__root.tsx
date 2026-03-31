import { createRootRoute, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";

export const Route = createRootRoute({
	component: RootLayout,
});

function RootLayout(): ReactNode {
	return <Outlet />;
}
