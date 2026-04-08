import { createFileRoute } from "@tanstack/react-router";
import { CatalogLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/markets/screener")({
	component: ScreenerPage,
	handle: { title: "市场筛选" },
});

function ScreenerPage() {
	return (
		<CatalogLayout
			toolbar={<Placeholder label="Filter Toolbar" />}
			main={<Placeholder label="Screener Table" />}
			detail={<Placeholder label="Detail Panel" />}
		/>
	);
}
