import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";

const STRATEGY_ROWS = [
	["strat-001", "多因子动量策略 v3", "completed"],
	["strat-002", "低波红利轮动", "running"],
	["strat-003", "行业中性 Alpha", "draft"],
] as const;

export function StrategyListPage() {
	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">策略列表</p>
						<p className="text-xs text-(--color-foreground-tertiary)">研究策略、版本和上线状态</p>
					</div>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Strategies" count={STRATEGY_ROWS.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{STRATEGY_ROWS.map(([id, name, state]) => (
								<div key={id} className="grid grid-cols-[7rem_1fr_6rem] items-center px-3 py-2 text-sm">
									<span className="font-data text-(--color-foreground-tertiary)">{id}</span>
									<span className="text-(--color-foreground)">{name}</span>
									<span className="font-data text-(--color-foreground-secondary)">{state}</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Promotion" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择策略后显示发布门禁、最近回测和依赖因子。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
