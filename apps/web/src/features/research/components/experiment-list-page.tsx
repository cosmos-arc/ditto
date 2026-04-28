import { OpsConsoleLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";

const EXPERIMENTS = [
	["exp-1042", "A 股小盘反转参数扫描", "running"],
	["exp-1039", "行业中性约束回归", "queued"],
	["exp-1035", "财报窗口过滤", "completed"],
] as const;

export function ExperimentListPage() {
	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={
					<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<p className="text-sm font-medium text-(--color-foreground)">实验队列</p>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">1 running</span>
					</div>
				}
				main={
					<Panel className="m-4">
						<PanelHeader title="Experiments" count={EXPERIMENTS.length} />
						<PanelBody>
							<div className="divide-y divide-(--color-border-subtle)">
								{EXPERIMENTS.map(([id, name, status]) => (
									<div key={id} className="grid grid-cols-[7rem_1fr_6rem] items-center px-3 py-2 text-sm">
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
						<PanelHeader title="Run Detail" />
						<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
							实验详情、资源占用和失败重试记录在此汇总。
						</PanelBody>
					</Panel>
				}
			/>
			<StatusBar />
		</>
	);
}
