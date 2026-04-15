import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { RegimeCurrentView } from "./regime-current-view";
import { RegimeHistoryList } from "./regime-history-list";
import { RegimeStrategyImpact } from "./regime-strategy-impact";

export function RegimePage() {
	return (
		<>
		<AnalyticalLayout
			className="pb-(--height-status-bar)"
			strip={
				<div data-info-level="l1" data-info-unit="regime-strip" className="flex items-center gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
					<span className="text-xs font-medium text-(--color-foreground-tertiary)">Regime Monitor</span>
					<span className="text-xs text-(--color-foreground-muted)">|</span>
					<span className="text-xs text-(--color-foreground-secondary)">市场状态追踪与策略影响分析</span>
				</div>
			}
			main={
				<div className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)">
					<div data-info-level="l1" data-info-unit="regime-current">
						<RegimeCurrentView />
					</div>
					<div data-info-level="l1" data-info-unit="regime-history">
						<RegimeHistoryList />
					</div>
				</div>
			}
			activity={
				<div data-info-level="l2" data-info-unit="regime-strategy-impact">
					<Panel>
						<PanelHeader title="策略影响" />
						<PanelBody className="p-3">
							<RegimeStrategyImpact />
						</PanelBody>
					</Panel>
				</div>
			}
			analysis={
				<div className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
					<span className="text-xs text-(--color-foreground-tertiary)">分析面板 · 待实现</span>
				</div>
			}
		/>
		<StatusBar />
		</>
	);
}
