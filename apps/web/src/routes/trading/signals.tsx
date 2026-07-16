import { createFileRoute } from "@tanstack/react-router";
import { SignalsPage } from "@/features/trading";

export const Route = createFileRoute("/trading/signals")({
	component: SignalsPage,
	staticData: { title: "信号收件箱" },
});
