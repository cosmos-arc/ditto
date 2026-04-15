import { CatalogLayout } from "@/features/shell";
import { FilterToolbar } from "@/components/domain/filter-controls/filter-toolbar";
import { MarketCalendarList } from "./market-calendar-list";

function CalendarToolbar() {
	return (
		<FilterToolbar>
			<span className="px-2 text-sm font-medium text-(--color-foreground-secondary)">
				市场日历
			</span>
		</FilterToolbar>
	);
}

export function CalendarPage() {
	return (
		<CatalogLayout
			toolbar={<div data-info-level="l1" data-info-unit="calendar-toolbar"><CalendarToolbar /></div>}
			main={<div data-info-level="l2" data-info-unit="calendar-main"><MarketCalendarList /></div>}
		/>
	);
}
