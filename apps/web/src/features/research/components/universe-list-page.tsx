import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";

const UNIVERSES = [
	["沪深300", "300 symbols", "daily"],
	["中证500", "500 symbols", "daily"],
	["高股息精选", "86 symbols", "weekly"],
] as const;

export function UniverseListPage() {
	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">股票池</p>
						<p className="text-xs text-(--color-foreground-tertiary)">研究、回测和交易共享的 universe 定义</p>
					</div>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Universes" count={UNIVERSES.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{UNIVERSES.map(([name, size, cadence]) => (
								<div key={name} className="grid grid-cols-[1fr_7rem_5rem] items-center px-3 py-2 text-sm">
									<span className="text-(--color-foreground)">{name}</span>
									<span className="font-data text-(--color-foreground-tertiary)">{size}</span>
									<span className="font-data text-(--color-foreground-tertiary)">{cadence}</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Rules" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择股票池后显示纳入规则、排除条件和最近一次重平衡。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
