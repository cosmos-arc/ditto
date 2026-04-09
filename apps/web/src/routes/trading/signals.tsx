import { createFileRoute } from "@tanstack/react-router";
import { SignalsPage } from "@/features/trading";

export const Route = createFileRoute("/trading/signals")({
	component: SignalsPage,
	handle: { title: "信号收件箱" },
});
