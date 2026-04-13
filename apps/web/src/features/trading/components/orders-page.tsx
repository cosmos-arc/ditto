import { OpsConsoleLayout, StatusBar } from "@/features/shell";
import { OrdersList } from "./orders-list";
import { OrdersHealthStrip } from "./orders-health-strip";
import { OrderDetailPanel } from "./order-detail-panel";

const DEFAULT_ORDER_ID = "ord-003";

export function OrdersPage() {
	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={<OrdersHealthStrip />}
				main={<OrdersList />}
				detail={
					<div className="h-full overflow-y-auto">
						<OrderDetailPanel orderId={DEFAULT_ORDER_ID} />
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
