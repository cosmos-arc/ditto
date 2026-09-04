import { createFileRoute } from "@tanstack/react-router";
import { SelectionWorkspacePage } from "@/features/selection";

export const Route = createFileRoute("/markets/screener")({
	component: SelectionWorkspacePage,
	staticData: { title: "Selection Workspace" },
});
