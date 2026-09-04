import { createFileRoute } from "@tanstack/react-router";
import { DataProductWorkbench } from "@/features/data-products";
import { StatusBar } from "@/features/shell";

export const Route = createFileRoute("/system/data-products")({
	component: DataProductsPage,
	staticData: { title: "数据产品" },
});

function DataProductsPage() {
	return (
		<>
			<DataProductWorkbench />
			<StatusBar />
		</>
	);
}
