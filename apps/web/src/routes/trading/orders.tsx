import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/trading/orders")({
	component: OrdersPage,
	handle: { title: "订单台账" },
});

function OrdersPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Orders Ledger — 占位
		</div>
	);
}
