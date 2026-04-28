import { OpsConsoleLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";

const SETTINGS = [
	["数据源", "已连接"],
	["交易网关", "只读模式"],
	["通知策略", "启用"],
] as const;

export function PlatformSettingsPage() {
	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={
					<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<p className="text-sm font-medium text-(--color-foreground)">平台设置</p>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">3 groups</span>
					</div>
				}
				main={
					<Panel className="m-4">
						<PanelHeader title="Settings" />
						<PanelBody>
							<div className="divide-y divide-(--color-border-subtle)">
								{SETTINGS.map(([name, state]) => (
									<div key={name} className="grid grid-cols-[1fr_7rem] items-center px-3 py-2 text-sm">
										<span className="text-(--color-foreground)">{name}</span>
										<span className="font-data text-(--color-foreground-tertiary)">{state}</span>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
				}
				detail={
					<Panel className="m-4 ml-0">
						<PanelHeader title="Change Log" />
						<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
							配置变更、审批状态和回滚点在此呈现。
						</PanelBody>
					</Panel>
				}
			/>
			<StatusBar />
		</>
	);
}
