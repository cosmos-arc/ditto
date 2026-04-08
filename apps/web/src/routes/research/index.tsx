import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/")({
	component: ResearchPage,
	handle: { title: "研究" },
});

function ResearchPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Research — 占位
		</div>
	);
}
