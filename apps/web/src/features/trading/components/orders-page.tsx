import { useState } from "react";
import { OpsConsoleLayout, StatusBar } from "@/features/shell";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { OrdersHealthStrip } from "./orders-health-strip";
import { OrdersList } from "./orders-list";
import { OrderDetailPanel } from "./order-detail-panel";

export function OrdersPage() {
	const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={<OrdersHealthStrip />}
				main={<OrdersList onSelectOrder={setSelectedOrderId} />}
			/>
			<StatusBar />
			<Drawer
				open={selectedOrderId !== null}
				onClose={() => setSelectedOrderId(null)}
				title="订单详情"
			>
				<div data-info-level="l3" data-info-unit="order-detail">
					{selectedOrderId && <OrderDetailPanel orderId={selectedOrderId} />}
				</div>
			</Drawer>
		</>
	);
}
