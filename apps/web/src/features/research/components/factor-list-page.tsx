import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";

const FACTOR_ROWS = [
	["momentum", "动量因子", "active"],
	["volatility", "波动率因子", "active"],
	["northbound", "北向资金因子", "draft"],
] as const;

export function FactorListPage() {
	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">因子库</p>
						<p className="text-xs text-(--color-foreground-tertiary)">研究因子的质量、版本和可用性</p>
					</div>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Factors" count={FACTOR_ROWS.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{FACTOR_ROWS.map(([id, name, status]) => (
								<div key={id} className="grid grid-cols-[1fr_6rem] items-center px-3 py-2 text-sm">
									<span className="text-(--color-foreground)">{name}</span>
									<span className="font-data text-(--color-foreground-tertiary)">{status}</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Factor Detail" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择因子后显示 IC、换手和覆盖率摘要。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
