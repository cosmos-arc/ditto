import { useState } from "react";
import { FilterToolbar } from "@/components/domain/filter-controls/filter-toolbar";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { MarketCalendarList } from "./market-calendar-list";
import { CalendarOverlay, type CalendarOverlayId, calendarActions } from "./market-page-overlays";
import type { MarketCalendarStatusQuery } from "./market-view-contracts";

function CalendarToolbar({ onOpen }: { readonly onOpen: (id: CalendarOverlayId) => void }) {
	return (
		<FilterToolbar>
			<div className="min-w-0 flex-1 px-2">
				<p className="text-sm font-medium text-(--color-foreground-secondary)">交易日历数据状态</p>
				<p className="text-xs text-(--color-foreground-tertiary)">
					数据源：ingestion status · 只显示最新摄取与目录新鲜度
				</p>
			</div>
			<PageActionBar ariaLabel="日历页面操作" actions={calendarActions} onOpen={onOpen} />
		</FilterToolbar>
	);
}

export function CalendarPage({ status }: { readonly status: MarketCalendarStatusQuery }) {
	const [activeOverlay, setActiveOverlay] = useState<CalendarOverlayId | null>(null);
	return (
		<>
			<CatalogLayout
				toolbar={
					<div data-info-level="l1" data-info-unit="calendar-toolbar">
						<CalendarToolbar onOpen={setActiveOverlay} />
					</div>
				}
				main={
					<div data-info-level="l2" data-info-unit="calendar-main">
						<MarketCalendarList query={status} />
					</div>
				}
				detail={
					<Panel className="m-4 ml-0" data-info-level="l2" data-info-unit="calendar-boundary">
						<PanelHeader title="查询边界" subtitle="ingestion status only" />
						<PanelBody className="space-y-3 p-(--density-panel-padding) text-sm leading-6 text-(--color-foreground-secondary)">
							<p>数据集：calendar</p>
							<p>数据源：/api/v1/ingestion/status</p>
							<p className="text-(--color-foreground-tertiary)">
								当前公开合同提供最新摄取日期、状态、记录数与 catalog 新鲜度，不提供宏观事件标题、发布时间或预期值。
							</p>
						</PanelBody>
					</Panel>
				}
			/>
			<CalendarOverlay active={activeOverlay} onClose={() => setActiveOverlay(null)} />
		</>
	);
}
