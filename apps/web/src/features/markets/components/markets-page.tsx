import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { useMarketContext } from "../hooks";
import { MarketCardGrid } from "./market-card-grid";
import { MacroDriversBar } from "./macro-drivers-bar";
import { CapitalRotationTable } from "./capital-rotation-table";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

function ContextBar() {
	const { data, isLoading, isError, refetch } = useMarketContext();

	if (isLoading) return <LoadingSkeleton variant="metric" className="h-8" />;

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div className="flex items-center gap-4 px-4 py-2 text-xs">
				<span>市态: <strong>{data?.regime ?? "—"}</strong></span>
				<span>波动: <strong>{data?.volatility ?? "—"}%</strong></span>
				<span>美元: <strong>{data?.usdStrength ?? "—"}</strong></span>
				{data && data.alertCount > 0 && (
					<span className="text-(--color-status-warning)">{data.alertCount} 预警</span>
				)}
			</div>
		</DittoErrorBoundary>
	);
}

const MOCK_EVENTS = [
	{ text: "科技板块资金净流入 +12.3 亿", time: "5分钟前", severity: "up" as const },
	{ text: "北向资金转为净卖出", time: "15分钟前", severity: "down" as const },
	{ text: "沪深300 期权 PCR 升至 1.2", time: "30分钟前", severity: "neutral" as const },
	{ text: "创业板指突破 2100 关口", time: "1小时前", severity: "up" as const },
];

const MOCK_FLOWS = [
	{ sector: "科技", flow: "+12.3亿", dir: "up" as const },
	{ sector: "消费", flow: "+5.8亿", dir: "up" as const },
	{ sector: "金融", flow: "-3.2亿", dir: "down" as const },
	{ sector: "医药", flow: "+2.1亿", dir: "up" as const },
	{ sector: "新能源", flow: "-8.5亿", dir: "down" as const },
];

export function MarketsPage() {
	return (
		<AnalyticalLayout
			strip={<ContextBar />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<MarketCardGrid />
					<MacroDriversBar />
					<CapitalRotationTable />
				</div>
			}
			activity={
				<Panel>
					<PanelHeader
						title="市场事件"
						actions={
							<button type="button" className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-(--radius-sm) px-1.5 py-0.5">
								查看全部 →
							</button>
						}
					/>
					<PanelBody className="p-3">
						<div className="flex flex-col gap-1">
							{MOCK_EVENTS.map((event, i) => (
								<div
									key={i}
									className="flex items-center justify-between rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<span
										className={`inline-block size-1.5 shrink-0 rounded-full ${event.severity === "up" ? "bg-(--color-market-up-fg)" : event.severity === "down" ? "bg-(--color-market-down-fg)" : "bg-(--color-foreground-muted)"}`}
									/>
									<span className="min-w-0 flex-1 truncate text-xs text-(--color-foreground)">
										{event.text}
									</span>
									<span className="shrink-0 text-[10px] tabular-nums text-(--color-foreground-muted)">
										{event.time}
									</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			analysis={
				<Panel>
					<PanelHeader title="资金流向" />
					<PanelBody className="p-3">
						<div className="flex flex-col gap-1">
							{MOCK_FLOWS.map((item) => (
								<div
									key={item.sector}
									className="flex items-center justify-between rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<span className="text-xs text-(--color-foreground-secondary)">
										{item.sector}
									</span>
									<span
										className={`font-(--font-data) text-xs tabular-nums ${item.dir === "up" ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}
									>
										{item.flow}
									</span>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}
