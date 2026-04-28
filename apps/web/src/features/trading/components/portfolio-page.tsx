import { AnalyticalLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";

const PORTFOLIO_ROWS = [
	["权益", "68.2%", "+1.4%"],
	["债券", "18.5%", "+0.2%"],
	["现金", "13.3%", "0.0%"],
] as const;

export function PortfolioPage() {
	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={
					<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<p className="text-sm font-medium text-(--color-foreground)">组合总览</p>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">T+0 exposure</span>
					</div>
				}
				main={
					<Panel className="m-4">
						<PanelHeader title="Allocation" />
						<PanelBody>
							<div className="divide-y divide-(--color-border-subtle)">
								{PORTFOLIO_ROWS.map(([asset, weight, pnl]) => (
									<div key={asset} className="grid grid-cols-[1fr_5rem_5rem] items-center px-3 py-2 text-sm">
										<span className="text-(--color-foreground)">{asset}</span>
										<span className="font-data text-(--color-foreground-tertiary)">{weight}</span>
										<span className="font-data text-(--color-market-up-fg)">{pnl}</span>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
				}
				activity={
					<Panel className="m-4 ml-0">
						<PanelHeader title="Activity" />
						<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
							最近调仓、资金流和执行偏离。
						</PanelBody>
					</Panel>
				}
				analysis={
					<div className="border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2 text-xs text-(--color-foreground-tertiary)">
						风险预算、回撤贡献和行业偏离在此汇总。
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
