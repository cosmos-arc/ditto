import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { DashboardShell } from "@/features/dashboard/components/dashboard-shell";
import "@/styles/globals.css";

createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<DashboardShell />
	</StrictMode>,
);
