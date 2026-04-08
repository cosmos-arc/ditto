import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/trading/risk")({
	component: RiskPage,
	handle: { title: "风控中心" },
});

function RiskPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Risk Center — 占位
		</div>
	);
}
