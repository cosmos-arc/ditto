import { CatalogLayout } from "@/features/shell";
import { MarketCalendarList } from "./market-calendar-list";

export function CalendarPage() {
	return (
		<CatalogLayout
			main={<MarketCalendarList />}
		/>
	);
}
