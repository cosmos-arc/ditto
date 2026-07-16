import { createFileRoute } from "@tanstack/react-router";
import { OrdersPage } from "@/features/trading";

export const Route = createFileRoute("/trading/orders")({
	component: OrdersPage,
	staticData: { title: "订单台账" },
});
