import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { OpsConsoleLayout, OverlayProvider, StatusBar, useOverlayController } from "@/features/shell";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { FillLedgerList } from "./fill-ledger-list";
import { OrderDetailPanel } from "./order-detail-panel";
import { OrdersHealthStrip } from "./orders-health-strip";
import { OrdersList } from "./orders-list";
import { SignalToOrderPipelineStrip } from "./signal-to-order-pipeline-strip";

const ORDER_DETAIL_OVERLAY_ID = "orders.detail";

export function OrdersPage() {
	if (!shouldUsePrototypeMocks()) {
		return (
			<>
				<OpsConsoleLayout
					className="pb-(--height-status-bar)"
					health={<SignalToOrderPipelineStrip />}
					main={<FillLedgerList />}
				/>
				<StatusBar />
			</>
		);
	}

	return (
		<OverlayProvider>
			<OrdersPageContent />
		</OverlayProvider>
	);
}

function OrdersPageContent() {
	const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();

	function handleSelectOrder(orderId: string) {
		setSelectedOrderId(orderId);
		openOverlay(ORDER_DETAIL_OVERLAY_ID);
	}

	function handleCloseOrderDetail() {
		closeOverlay();
		setSelectedOrderId(null);
	}

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={<OrdersHealthStrip />}
				main={<OrdersList onSelectOrder={handleSelectOrder} />}
			/>
			<StatusBar />
			<Drawer
				open={activeOverlayId === ORDER_DETAIL_OVERLAY_ID && selectedOrderId !== null}
				onClose={handleCloseOrderDetail}
				title="订单详情"
			>
				<div data-info-level="l3" data-info-unit="order-detail">
					{selectedOrderId && <OrderDetailPanel orderId={selectedOrderId} />}
				</div>
			</Drawer>
		</>
	);
}
