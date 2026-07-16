import { Fragment, useState } from "react";
import { Metric } from "@/components/data";

/* ── Types ── */

type TabId = "ic-trends" | "factor-breadth" | "correlation" | "notes";

interface TabDef {
	readonly id: TabId;
	readonly label: string;
}

/* ── Constants ── */

const TABS: readonly TabDef[] = [
	{ id: "ic-trends", label: "IC Trends" },
	{ id: "factor-breadth", label: "因子宽度" },
	{ id: "correlation", label: "相关性" },
	{ id: "notes", label: "笔记" },
] as const;

const IC_METRICS = [
	{ label: "IC均值", value: "0.053" },
	{ label: "IC_IR", value: "1.24" },
	{ label: "IC胜率", value: "62%" },
] as const;

const BARS: readonly number[] = [0.65, 0.42, 0.78, 0.35, 0.91, 0.55];

const CORRELATION_FACTORS = [
	{ label: "动量12M", short: "动" },
	{ label: "价值PE", short: "价" },
	{ label: "低波动", short: "低" },
	{ label: "北向持仓", short: "北" },
	{ label: "情绪Alpha", short: "情" },
] as const;

const CORRELATION_MATRIX: readonly (readonly number[])[] = [
	[1.0, -0.12, -0.18, 0.25, 0.72],
	[-0.12, 1.0, 0.31, 0.08, -0.05],
	[-0.18, 0.31, 1.0, 0.14, -0.22],
	[0.25, 0.08, 0.14, 1.0, 0.38],
	[0.72, -0.05, -0.22, 0.38, 1.0],
];

const NOTES: readonly { readonly id: string; readonly text: string; readonly time: string }[] = [
	{ id: "1", text: "动量因子 IC 近 5 日持续走强，建议关注", time: "10:30" },
	{ id: "2", text: "价值因子衰减加快，需评估换手率影响", time: "09:15" },
	{ id: "3", text: "情绪因子 v2 已进入审核队列", time: "昨日" },
];

/* ── Sub-components ── */

function IcTrendsPanel() {
	return (
		<div className="p-3">
			<div className="flex gap-4">
				{IC_METRICS.map((m) => (
					<Metric key={m.label} variant="strip" label={m.label} value={m.value} />
				))}
			</div>
			<svg viewBox="0 0 200 60" className="mt-2 w-full" aria-label="IC 趋势图">
				<polyline
					fill="none"
					stroke="var(--color-chart-1)"
					strokeWidth="1.5"
					points="0,40 33,32 66,44 100,28 133,35 166,22 200,30"
				/>
			</svg>
		</div>
	);
}

function FactorBreadthPanel() {
	const maxVal = Math.max(...BARS);
	return (
		<div className="p-3">
			<svg viewBox="0 0 120 50" className="w-full" aria-label="因子宽度柱状图">
				{BARS.map((val, i) => {
					const barHeight = (val / maxVal) * 40;
					return (
						<rect
							key={`bar-${val}`}
							data-bar=""
							x={i * 20}
							y={45 - barHeight}
							width={14}
							height={barHeight}
							rx={2}
							fill="var(--color-chart-1)"
							opacity={0.6 + (val / maxVal) * 0.4}
						/>
					);
				})}
			</svg>
		</div>
	);
}

function correlationCellClass(value: number, row: number, col: number): string {
	if (row === col) {
		return "self bg-(--color-surface-2) text-(--color-foreground-muted) ring-1 ring-(--color-border-subtle)";
	}
	if (value >= 0.65) {
		return "signal accent bg-(--color-accent)/20 text-(--color-accent) ring-1 ring-(--color-accent)/35";
	}
	if (value >= 0.3) {
		return "moderate bg-(--color-accent)/10 text-(--color-foreground-secondary)";
	}
	if (value <= -0.3) {
		return "negative bg-(--color-status-led-critical)/16 text-(--color-status-led-critical)";
	}
	if (value <= -0.1) {
		return "negative-muted bg-(--color-status-led-critical)/8 text-(--color-foreground-tertiary)";
	}
	return "muted bg-(--color-surface-1) text-(--color-foreground-muted)";
}

function correlationCellText(value: number, row: number, col: number): string {
	if (row === col) return "•";
	if (Math.abs(value) >= 0.65) return value.toFixed(2);
	return "";
}

function CorrelationPanel() {
	return (
		<div className="p-3">
			<div className="mb-2 flex items-center justify-between gap-3">
				<span className="text-xs text-(--color-foreground-tertiary)">强相关焦点</span>
				<span className="font-data text-xs tabular-nums text-(--color-accent)">动量/情绪 0.72</span>
			</div>
			<div className="flex items-center gap-4">
				<div className="grid grid-cols-[2rem_repeat(5,1.75rem)] gap-1 font-data text-xs">
					<div aria-hidden="true" />
					{CORRELATION_FACTORS.map((factor) => (
						<div key={`x-${factor.label}`} className="text-center text-(--color-foreground-tertiary)">
							{factor.short}
						</div>
					))}
					{CORRELATION_MATRIX.map((row, rowIdx) => (
						<Fragment key={`row-${CORRELATION_FACTORS[rowIdx]?.label ?? rowIdx}`}>
							<div className="flex items-center text-(--color-foreground-tertiary)">
								{CORRELATION_FACTORS[rowIdx]?.short}
							</div>
							{row.map((value, colIdx) => {
								const rowLabel = CORRELATION_FACTORS[rowIdx]?.label ?? `因子 ${rowIdx + 1}`;
								const colLabel = CORRELATION_FACTORS[colIdx]?.label ?? `因子 ${colIdx + 1}`;
								const toneClass = correlationCellClass(value, rowIdx, colIdx);
								return (
									<div
										key={`hm-${rowLabel}-${colLabel}`}
										data-heatmap-cell=""
										data-correlation-tone={toneClass.split(" ")[0]}
										role="img"
										className={[
											"flex h-7 w-7 items-center justify-center rounded-[3px] text-xs tabular-nums transition-transform hover:scale-110",
											toneClass,
										].join(" ")}
										aria-label={`${rowLabel} vs ${colLabel}: 相关系数 ${value.toFixed(2)}`}
										title={`${rowLabel} vs ${colLabel} · 相关系数 ${value.toFixed(2)}`}
									>
										{correlationCellText(value, rowIdx, colIdx)}
									</div>
								);
							})}
						</Fragment>
					))}
				</div>
				<div className="flex items-center gap-1 font-data text-xs text-(--color-foreground-tertiary)">
					<span>-1</span>
					<div className="h-1.5 w-14 rounded-full bg-linear-to-r from-(--color-status-led-critical)/35 via-(--color-surface-1) to-(--color-accent)/45" />
					<span>+1</span>
				</div>
			</div>
		</div>
	);
}

function NotesPanel() {
	return (
		<ul className="p-3">
			{NOTES.map((note) => (
				<li key={note.id} data-note-item="" className="flex items-start gap-2 py-1.5">
					<span className="text-xs text-(--color-foreground-tertiary) shrink-0 tabular-nums font-data">
						{note.time}
					</span>
					<span className="text-xs text-(--color-foreground-secondary)">{note.text}</span>
				</li>
			))}
		</ul>
	);
}

const PANEL_MAP: Record<TabId, () => React.JSX.Element> = {
	"ic-trends": IcTrendsPanel,
	"factor-breadth": FactorBreadthPanel,
	correlation: CorrelationPanel,
	notes: NotesPanel,
};

/* ── Main Component ── */

export function AnalysisBand() {
	const [activeTab, setActiveTab] = useState<TabId>("ic-trends");
	const Panel = PANEL_MAP[activeTab];

	return (
		<div data-slot="analysis-band">
			<div role="tablist" className="flex gap-1 border-b border-(--color-border-subtle) px-2 py-1">
				{TABS.map((tab) => {
					const isActive = tab.id === activeTab;
					return (
						<button
							key={tab.id}
							type="button"
							role="tab"
							aria-selected={isActive}
							className={[
								"px-3 py-1.5 rounded-md text-xs transition-colors",
								isActive
									? "bg-(--color-surface-2) text-(--color-foreground) font-medium"
									: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg)",
							].join(" ")}
							onClick={() => setActiveTab(tab.id)}
						>
							{tab.label}
						</button>
					);
				})}
			</div>
			<div role="tabpanel">
				<Panel />
			</div>
		</div>
	);
}
