import { OpsConsoleLayout, StatusBar } from "@/features/shell";
import { ConfidenceBar } from "@/components/indicator";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { HealthStrip } from "./health-strip";
import { ProviderTable } from "./provider-table";
import { PipelineTable } from "./pipeline-table";
import { AlertList } from "./alert-list";

const MOCK_TASKS = [
	{ name: "日线行情同步", meta: "Tushare + Wind", status: "running" as const, detail: "运行中 · 剩余 2 分钟" },
	{ name: "财务数据更新", meta: "东方财富 Choice", status: "waiting" as const, detail: "排队中 · 第 2 位" },
	{ name: "因子计算 · 北向持仓变化率", meta: "计算中 67%", status: "progress" as const, detail: "计算中 · 积压 15 分钟" },
	{ name: "模型评分 · 情绪 Alpha v2", meta: "服务返回 503", status: "failed" as const, detail: "已失败 · 需重试" },
];

const MOCK_RESOURCES = [
	{ label: "API 配额 (Tushare)", value: "96.4% — 4,820/5,000", severity: "critical" as const, width: 96 },
	{ label: "CPU 使用率", value: "23%", severity: "ok" as const, width: 23 },
	{ label: "内存使用", value: "4.2 / 16 GB", severity: "ok" as const, width: 26 },
	{ label: "磁盘空间", value: "128 / 512 GB", severity: "ok" as const, width: 25 },
];

const MOCK_EVENTS = [
	{ time: "14:32:15", text: "Tushare 日线数据同步完成" },
	{ time: "14:31:00", text: "Wind 分钟线采集启动" },
	{ time: "14:28:33", text: "因子计算 · 北向持仓变化率 开始" },
	{ time: "14:25:10", text: "模型评分 · 情绪 Alpha v2 失败" },
];

export function PlatformPage() {
	return (
		<>
		<OpsConsoleLayout
			className="pb-(--height-status-bar)"
			health={<HealthStrip />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<ProviderTable />
					<PipelineTable />
					<AlertList />
				</div>
			}
			detail={
				<div className="flex flex-col overflow-hidden">
					{/* 管道与任务 */}
					<Panel className="flex-1" data-info-level="l2" data-info-unit="tasks">
						<PanelHeader title="管道与任务" count={2} />
						<PanelBody className="p-3">
							<div className="flex flex-col gap-1">
								{MOCK_TASKS.map((task) => (
									<div
										key={task.name}
										className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<span className={`text-xs ${task.status === "running" ? "text-(--color-system-healthy-fg)" : task.status === "waiting" ? "text-(--color-foreground-muted)" : task.status === "progress" ? "text-(--color-system-degraded-fg)" : "text-(--color-system-down-fg)"}`}>
											{task.status === "running" ? "●" : task.status === "failed" ? "✕" : "○"}
										</span>
										<div className="flex min-w-0 flex-1 flex-col">
											<span className="text-xs text-(--color-foreground)">{task.name}</span>
											<span className="text-xs text-(--color-foreground-muted)">{task.meta}</span>
										</div>
										<span className={`shrink-0 text-xs ${task.status === "failed" ? "text-(--color-system-down-fg)" : "text-(--color-foreground-muted)"}`}>
											{task.detail}
										</span>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
					{/* 资源与配额 */}
					<Panel className="flex-1" data-info-level="l2" data-info-unit="resources">
						<PanelHeader title="资源与配额" />
						<PanelBody className="p-3">
							<div className="flex flex-col gap-2">
								{MOCK_RESOURCES.map((res) => (
									<div key={res.label} className="flex flex-col gap-1">
										<div className="flex items-center justify-between">
											<span className="text-xs text-(--color-foreground-secondary)">{res.label}</span>
											<span className={`text-xs tabular-nums ${res.severity === "critical" ? "text-(--color-risk-critical-fg)" : "text-(--color-system-healthy-fg)"}`}>
												{res.value}
											</span>
										</div>
										<ConfidenceBar
											value={res.width}
											color={res.severity === "critical" ? "danger" : "success"}
											size="sm"
											aria-label={`${res.label} usage`}
										/>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
					{/* 最近事件 */}
					<Panel className="flex-1" data-info-level="l2" data-info-unit="events">
						<PanelHeader title="最近事件" />
						<PanelBody className="p-3">
							<div className="flex flex-col gap-1">
								{MOCK_EVENTS.map((evt) => (
									<div
										key={`${evt.time}-${evt.text}`}
										className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<span className="shrink-0 text-xs tabular-nums text-(--color-foreground-muted)">{evt.time}</span>
										<span className="min-w-0 flex-1 truncate text-xs text-(--color-foreground-secondary)">{evt.text}</span>
									</div>
								))}
							</div>
						</PanelBody>
					</Panel>
				</div>
			}
		/>
		<StatusBar />
		</>
	);
}
