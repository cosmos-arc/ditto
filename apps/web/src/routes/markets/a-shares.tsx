import { createFileRoute } from "@tanstack/react-router";
import { ASharesPage } from "@/features/markets";

export const Route = createFileRoute("/markets/a-shares")({
	component: ASharesPage,
	handle: { title: "A股总览" },
});
