import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/instruments/$id")({
	component: InstrumentHubPage,
	handle: { title: "标的详情" },
});

function InstrumentHubPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Instrument Hub — 占位
		</div>
	);
}
