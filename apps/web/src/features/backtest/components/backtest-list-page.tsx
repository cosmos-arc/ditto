import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";

const BACKTEST_ROWS = [
	["bt-240427-a", "动量策略 v3", "completed"],
	["bt-240426-c", "低波红利组合", "completed"],
	["bt-240426-b", "北向资金增强", "failed"],
] as const;

export function BacktestListPage() {
	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">回测列表</p>
						<p className="text-xs text-(--color-foreground-tertiary)">策略验证结果和可复现实验记录</p>
					</div>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Backtests" count={BACKTEST_ROWS.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{BACKTEST_ROWS.map(([id, name, status]) => (
								<div key={id} className="grid grid-cols-[8rem_1fr_6rem] items-center px-3 py-2 text-sm">
									<span className="font-data text-(--color-foreground-tertiary)">{id}</span>
									<span className="text-(--color-foreground)">{name}</span>
									<span className="font-data text-(--color-foreground-secondary)">{status}</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Result Preview" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择回测后显示收益曲线、风险摘要和交易样本。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
