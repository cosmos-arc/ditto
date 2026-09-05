import { useState } from "react";
import { FilterToolbar } from "@/components/domain/filter-controls/filter-toolbar";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { MarketCalendarList } from "./market-calendar-list";
import { CalendarOverlay, type CalendarOverlayId, calendarActions } from "./market-page-overlays";
import type { MarketCalendarCoverageQuery } from "./market-view-contracts";

function CalendarToolbar({ onOpen }: { readonly onOpen: (id: CalendarOverlayId) => void }) {
	return (
		<FilterToolbar>
			<div className="min-w-0 flex-1 px-2">
				<p className="text-sm font-medium text-(--color-foreground-secondary)">交易日历数据产品</p>
				<p className="text-xs text-(--color-foreground-tertiary)">profile: research_daily · 只显示覆盖与质量阻断</p>
			</div>
			<PageActionBar ariaLabel="日历页面操作" actions={calendarActions} onOpen={onOpen} />
		</FilterToolbar>
	);
}

export function CalendarPage({ coverage }: { readonly coverage: MarketCalendarCoverageQuery }) {
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
						<MarketCalendarList query={coverage} />
					</div>
				}
				detail={
					<Panel className="m-4 ml-0" data-info-level="l2" data-info-unit="calendar-boundary">
						<PanelHeader title="查询边界" subtitle="coverage only" />
						<PanelBody className="space-y-3 p-(--density-panel-padding) text-sm leading-6 text-(--color-foreground-secondary)">
							<p>数据集：calendar</p>
							<p>消费者配置：research_daily</p>
							<p className="text-(--color-foreground-tertiary)">
								当前公开合同提供覆盖里程碑与分区缺口，不提供宏观事件标题、发布时间或预期值。
							</p>
						</PanelBody>
					</Panel>
				}
			/>
			<CalendarOverlay active={activeOverlay} onClose={() => setActiveOverlay(null)} />
		</>
	);
}
