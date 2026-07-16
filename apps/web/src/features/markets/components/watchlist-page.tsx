import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";

const WATCHLIST_ROWS = [
	["600519", "贵州茅台", "+1.8%", "强势"],
	["300750", "宁德时代", "-0.6%", "观察"],
	["510300", "沪深300 ETF", "+0.4%", "跟踪"],
] as const;

export function WatchlistPage() {
	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">自选监控</p>
						<p className="text-xs text-(--color-foreground-tertiary)">价格、信号和风险标签统一扫描</p>
					</div>
					<span className="rounded-(--radius-sm) bg-(--color-surface-panel-base) px-2 py-1 font-data text-xs text-(--color-foreground-tertiary)">
						{WATCHLIST_ROWS.length} symbols
					</span>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Watchlist" subtitle="实时队列" />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{WATCHLIST_ROWS.map(([code, name, change, state]) => (
								<div key={code} className="grid grid-cols-[6rem_1fr_5rem_5rem] items-center px-3 py-2 text-sm">
									<span className="font-data text-(--color-foreground-secondary)">{code}</span>
									<span className="text-(--color-foreground)">{name}</span>
									<span className="font-data text-(--color-market-up-fg)">{change}</span>
									<span className="text-(--color-foreground-tertiary)">{state}</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Context" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择标的后显示流动性、新闻脉冲和策略暴露。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
