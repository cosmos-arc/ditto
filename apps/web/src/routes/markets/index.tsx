import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/markets/")({
	component: CrossMarketPage,
	handle: { title: "跨市场总览" },
});

function CrossMarketPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Cross-Market — 占位
		</div>
	);
}
