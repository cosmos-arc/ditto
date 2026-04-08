import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/trading/")({
	component: TradingOverviewPage,
	handle: { title: "交易总览" },
});

function TradingOverviewPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Trading Overview — 占位
		</div>
	);
}
