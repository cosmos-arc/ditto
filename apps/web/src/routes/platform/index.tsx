import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/platform/")({
	component: PlatformPage,
	handle: { title: "平台管理" },
});

function PlatformPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Platform — 占位
		</div>
	);
}
