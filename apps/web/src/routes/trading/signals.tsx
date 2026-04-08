import { createFileRoute } from "@tanstack/react-router";
import { CatalogLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/trading/signals")({
	component: SignalsPage,
	handle: { title: "信号收件箱" },
});

function SignalsPage() {
	return (
		<CatalogLayout
			toolbar={<Placeholder label="Filter Toolbar" />}
			main={<Placeholder label="Signals Queue" />}
			detail={<Placeholder label="Signal Detail" />}
		/>
	);
}
