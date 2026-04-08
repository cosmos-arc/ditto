import { createFileRoute, Outlet } from "@tanstack/react-router";
import { OpsConsoleLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/platform")({
	component: PlatformLayout,
	handle: { title: "平台管理" },
});

function PlatformLayout() {
	return (
		<OpsConsoleLayout
			health={<Placeholder label="Health Strip" />}
			main={<Outlet />}
			detail={<Placeholder label="Detail Panel" />}
		/>
	)
}
