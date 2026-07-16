import { createFileRoute } from "@tanstack/react-router";
import { CalendarPage } from "@/features/markets";

export const Route = createFileRoute("/markets/calendar")({
	component: CalendarPage,
	staticData: { title: "事件日历" },
});
