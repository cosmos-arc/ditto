import { Link } from "@tanstack/react-router";
import { useExperiments } from "@/features/research/hooks";
import { OpsConsoleLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";

export function ExperimentListPage() {
	const { data, isLoading } = useExperiments();
	const experiments = data ?? [];
	const runningCount = experiments.filter((e) => e.status === "running").length;

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				health={
					<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<p className="text-sm font-medium text-(--color-foreground)">实验队列</p>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">{runningCount} running</span>
					</div>
				}
				main={
					<Panel className="m-4">
						<PanelHeader
							title="Experiments"
							count={experiments.length}
							actions={
								<Link
									to="/research/experiments/new"
									className="rounded-(--radius-sm) bg-(--brand-accent) px-2 py-1 text-xs text-(--brand-accent-fg)"
								>
									创建实验
								</Link>
							}
						/>
						<PanelBody>
							<div className="divide-y divide-(--color-border-subtle)">
								{isLoading && experiments.length === 0 ? (
									<p className="px-3 py-2 text-sm text-(--color-foreground-tertiary)">加载中…</p>
								) : (
									experiments.map((e) => (
										<Link
											key={e.experimentId}
											to="/research/experiments/$id"
											params={{ id: e.experimentId }}
											className="grid grid-cols-[7rem_1fr_6rem] items-center px-3 py-2 text-sm hover:bg-(--color-interaction-hover-bg)"
										>
											<span className="font-data text-(--color-foreground-tertiary)">{e.experimentId}</span>
											<span className="text-(--color-foreground)">{e.stage}</span>
											<span className="font-data text-(--color-foreground-secondary)">{e.status}</span>
										</Link>
									))
								)}
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
