import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/regime")({
	component: RegimePage,
	handle: { title: "Regime Monitor" },
});

function RegimePage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Regime Monitor — 占位
		</div>
	);
}
