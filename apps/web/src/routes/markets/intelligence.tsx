import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/markets/intelligence")({
	component: MarketsIntelligencePage,
	handle: { title: "市场情报" },
});

function MarketsIntelligencePage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Markets Intelligence — 占位
		</div>
	);
}
