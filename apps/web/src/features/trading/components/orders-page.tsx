import { CatalogLayout } from "@/features/shell";
import { OrdersList } from "./orders-list";

export function OrdersPage() {
	return (
		<CatalogLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<OrdersList />
				</div>
			}
		/>
	);
}
