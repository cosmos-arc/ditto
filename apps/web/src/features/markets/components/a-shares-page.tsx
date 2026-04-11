import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { ASharesOverview } from "./a-shares-overview";

export function ASharesPage() {
	return (
		<AnalyticalLayout
			main={
				<div className="h-full overflow-y-auto p-(--density-panel-padding)">
					<ASharesOverview />
				</div>
			}
			activity={
				<Panel>
					<PanelHeader title="市场快照" />
					<PanelBody className="p-3">
						<div className="space-y-2 text-sm text-(--color-foreground-secondary)">
							<p>沪深两市成交额 1.12 万亿，较昨日放量 8.3%。涨跌比 2847:1936。</p>
							<p className="text-xs text-(--color-foreground-tertiary)">数据截至 15:00 收盘</p>
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}
