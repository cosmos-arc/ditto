import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { ASharesOverview } from "./a-shares-overview";

export function ASharesPage() {
	return (
		<AnalyticalLayout
			main={
				<div data-info-level="l1" data-info-unit="a-shares-main" className="h-full overflow-y-auto p-(--density-panel-padding)">
					<ASharesOverview />
				</div>
			}
			activity={
				<Panel data-info-level="l1" data-info-unit="market-snapshot">
					<PanelHeader title="市场快照" />
					<PanelBody data-info-level="l2" data-info-unit="snapshot-body" className="p-3">
						<div data-info-level="l2" data-info-unit="snapshot-detail" className="space-y-2 text-sm text-(--color-foreground-secondary)">
							<p>沪深两市成交额 1.12 万亿，较昨日放量 8.3%。涨跌比 2847:1936。</p>
							<p data-info-level="l3" data-info-unit="snapshot-timestamp" className="text-xs text-(--color-foreground-tertiary)">数据截至 15:00 收盘</p>
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}
