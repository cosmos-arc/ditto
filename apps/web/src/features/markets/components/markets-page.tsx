import { RadarLayout, StatusBar } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { useMarketContext } from "../hooks";
import { MarketCardGrid } from "./market-card-grid";
import { MacroDriversBar } from "./macro-drivers-bar";
import { CapitalRotationTable } from "./capital-rotation-table";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ContextBar, ContextBarItem, ContextBarSep } from "@/components/indicator/context-bar";
import { ContextSection } from "@/components/domain/context-section";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

/* ── Context Bar ── */

function MarketContextBar() {
	// L1: first-screen primary context metrics

	const { data, isLoading, isError, refetch } = useMarketContext();

	if (isLoading) return <LoadingSkeleton variant="metric" className="h-8" />;

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextBar>
				<ContextBarItem label="市态" value={data?.regime ?? "—"} />
				<ContextBarSep />
				<ContextBarItem label="波动" value={`${data?.volatility ?? "—"}%`} />
				<ContextBarSep />
				<ContextBarItem label="美元" value={data?.usdStrength ?? "—"} />
				{data && data.alertCount > 0 && (
					<>
						<ContextBarSep />
						<ContextBarItem label="预警" value={data.alertCount} color="down" />
					</>
				)}
			</ContextBar>
		</DittoErrorBoundary>
	);
}

/* ── Mock Data ── */

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

const MOCK_SCOPE_TEXT =
	"A股三大指数集体收涨，沪指涨0.85%报3,285点。北向资金净流入12.3亿，科技板块领涨。市场风险偏好持续回升，建议关注动量因子表现。";

const CORRELATION_LABELS = ["沪深300", "创业板", "恒生", "标普500"] as const;

const CORRELATION_MATRIX: ReadonlyArray<ReadonlyArray<number>> = [
	[1.00, 0.85, 0.62, 0.35],
	[0.85, 1.00, 0.55, 0.28],
	[0.62, 0.55, 1.00, 0.45],
	[0.35, 0.28, 0.45, 1.00],
];

function correlationCellClass(value: number): string {
	if (value >= 0.7) return "bg-(--color-accent)/15 text-(--color-accent) accent";
	if (value >= 0.4) return "bg-(--color-accent)/8 text-(--color-foreground-secondary) moderate";
	return "bg-(--color-surface-1) text-(--color-foreground-muted) muted";
}

/* ── Scope Strip (extracted to own slot) ── */

function ScopeStrip() {
	return (
		<div
			data-slot="scope-strip"
			data-testid="scope-strip"
			data-info-level="l1"
			data-info-unit="scope-strip"
			className="rounded-(--radius-sm) border-l-2 border-l-(--color-accent) bg-(--color-surface-1) px-3 py-2"
		>
			<span className="mb-1 block text-xs font-medium uppercase tracking-wide text-(--color-foreground-tertiary)">
				今日解读
			</span>
			<p className="text-base leading-relaxed text-(--color-foreground-secondary)">
				{MOCK_SCOPE_TEXT}
			</p>
		</div>
	);
}

/* ── Cross-Market Matrix ── */

function CrossMarketMatrix() {
	return (
		<ContextSection title="跨市场相关性" data-info-level="l2" data-info-unit="cross-market-matrix">
			<div
				data-slot="cross-market-matrix"
				data-testid="cross-market-matrix"
				className="overflow-x-auto pb-2"
			>
				<table className="w-full table-fixed border-collapse text-sm">
					<thead>
						<tr>
							<th className="p-1.5 text-left font-medium text-(--color-foreground-muted)" aria-label="行标签" />
							{CORRELATION_LABELS.map((label) => (
								<th key={label} className="p-1.5 text-center font-medium text-(--color-foreground-tertiary)">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{CORRELATION_MATRIX.map((row, rowIdx) => (
							<tr key={CORRELATION_LABELS[rowIdx]}>
								<td className="p-1.5 font-medium text-(--color-foreground-tertiary)">
									{CORRELATION_LABELS[rowIdx]}
								</td>
								{row.map((value, colIdx) => (
									<td
										key={`${rowIdx}-${colIdx}`}
										data-testid={`corr-${rowIdx}-${colIdx}`}
										className={`rounded-(--radius-sm) p-1.5 text-center font-data tabular-nums ${correlationCellClass(value)}`}
									>
										{value.toFixed(2)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</ContextSection>
	);
}

/* ── Right Rail ── */

function MarketRightRail() {
	return (
		<div className="flex flex-col">
			<Panel data-info-level="l1" data-info-unit="market-events">
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
								data-info-level="l3"
								data-info-unit="market-event-item"
								className="flex items-center justify-between rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span
									className={`inline-block size-1.5 shrink-0 rounded-full ${event.severity === "up" ? "bg-(--color-market-up-fg)" : event.severity === "down" ? "bg-(--color-market-down-fg)" : "bg-(--color-foreground-muted)"}`}
								/>
								<span className="min-w-0 flex-1 truncate text-xs text-(--color-foreground)">
									{event.text}
								</span>
								<span className="shrink-0 font-data text-xs tabular-nums text-(--color-foreground-muted)">
									{event.time}
								</span>
							</div>
						))}
					</div>
				</PanelBody>
			</Panel>
			<Panel data-info-level="l1" data-info-unit="capital-flows">
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
									className={`font-data text-xs tabular-nums ${item.dir === "up" ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}
								>
									{item.flow}
								</span>
							</div>
						))}
					</div>
				</PanelBody>
			</Panel>
		</div>
	);
}

/* ── Page ── */

export function MarketsPage() {
	return (
		<>
		<RadarLayout
			className="pb-(--height-status-bar)"
			contextBar={<MarketContextBar />}
			scopeStrip={<ScopeStrip />}
			main={
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<MarketCardGrid />
					<Tabs defaultValue="macro" className="flex flex-col gap-(--section-gap)">
						<TabsList>
							<TabsTrigger value="macro">宏观驱动</TabsTrigger>
							<TabsTrigger value="rotation">资金轮动</TabsTrigger>
							<TabsTrigger value="correlation">跨市场相关性</TabsTrigger>
						</TabsList>
						<TabsContent value="macro">
							<MacroDriversBar />
						</TabsContent>
						<TabsContent value="rotation">
							<CapitalRotationTable />
						</TabsContent>
						<TabsContent value="correlation">
							<CrossMarketMatrix />
						</TabsContent>
					</Tabs>
				</div>
			}
			rightRail={<MarketRightRail />}
		/>
		<StatusBar />
		</>
	);
}
