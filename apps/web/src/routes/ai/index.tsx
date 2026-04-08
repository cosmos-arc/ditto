import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/ai/")({
	component: AIOverviewPage,
	handle: { title: "AI Overview" },
});

function AIOverviewPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			AI Overview — 占位
		</div>
	);
}
