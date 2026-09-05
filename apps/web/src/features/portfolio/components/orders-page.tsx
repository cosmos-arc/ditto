import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { OpsConsoleLayout, OverlayProvider, StatusBar, useOverlayController } from "@/features/shell";
import { useOrders } from "../hooks";
import { FillLedgerList } from "./fill-ledger-list";
import { OrderDetailPanel } from "./order-detail-panel";
import { OrdersHealthStrip } from "./orders-health-strip";
import { OrdersList } from "./orders-list";
import { SignalToOrderPipelineStrip } from "./signal-to-order-pipeline-strip";

const ORDER_DETAIL_OVERLAY_ID = "orders.detail";

export function OrdersPage() {
	return (
		<OverlayProvider>
			<OrdersPageContent />
		</OverlayProvider>
	);
}

function OrdersPageContent() {
	const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
	const orders = useOrders();
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();
	const effectiveOrderId = selectedOrderId ?? orders.data?.items[0]?.id ?? null;

	function handleSelectOrder(orderId: string) {
		setSelectedOrderId(orderId);
		if (globalThis.matchMedia?.("(max-width: 899px)").matches ?? true) {
			openOverlay(ORDER_DETAIL_OVERLAY_ID);
		}
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
				main={
					<div className="h-full overflow-y-auto">
						<SignalToOrderPipelineStrip />
						<main
							className="min-h-[calc(100%-44px)]"
							data-info-unit="orders-ledger-main"
							data-testid="orders-ledger-main"
						>
							<OrdersList onSelectOrder={handleSelectOrder} />
							<FillLedgerList />
						</main>
					</div>
				}
				detail={
					<div
						className="h-full overflow-y-auto border-l border-t border-(--color-border-subtle) bg-(--color-surface-panel-base)"
						data-info-level="l3"
						data-info-unit="order-detail"
					>
						{effectiveOrderId ? (
							<OrderDetailPanel orderId={effectiveOrderId} />
						) : (
							<p className="p-(--density-panel-padding) text-sm text-(--color-foreground-tertiary)">当前没有订单意图</p>
						)}
					</div>
				}
			/>
			<StatusBar spanRail />
			<Drawer
				open={activeOverlayId === ORDER_DETAIL_OVERLAY_ID && effectiveOrderId !== null}
				onClose={handleCloseOrderDetail}
				title="订单详情"
			>
				<div data-info-level="l3" data-info-unit="order-detail">
					{effectiveOrderId && <OrderDetailPanel orderId={effectiveOrderId} />}
				</div>
			</Drawer>
		</>
	);
}
