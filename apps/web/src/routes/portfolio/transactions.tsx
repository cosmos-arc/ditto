import { createFileRoute } from "@tanstack/react-router";
import { OrdersPage } from "@/features/portfolio";

export const Route = createFileRoute("/portfolio/transactions")({
	component: OrdersPage,
	staticData: { title: "Paper Orders & Fills" },
});
