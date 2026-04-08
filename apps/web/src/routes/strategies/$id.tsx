import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/strategies/$id")({
	component: StrategyHubPage,
	handle: { title: "策略详情" },
});

function StrategyHubPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Strategy Hub — 占位
		</div>
	);
}
