import { useState } from "react";
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

const HEATMAP_LEVELS = 5;
const HEATMAP_SIZE = 5;

const HEATMAP_DATA: readonly (readonly number[])[] = [
	[4, 2, 0, 1, 3],
	[2, 4, 1, 0, 2],
	[0, 1, 4, 3, 1],
	[1, 0, 3, 4, 2],
	[3, 2, 1, 2, 4],
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
							key={`bar-${i}-${val}`}
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

function CorrelationPanel() {
	return (
		<div className="p-3">
			<div
				className="grid"
				style={{
					gridTemplateColumns: `repeat(${HEATMAP_SIZE}, 2rem)`,
					gap: "2px",
				}}
			>
				{Array.from({ length: HEATMAP_SIZE * HEATMAP_SIZE }, (_, idx) => {
					const row = Math.floor(idx / HEATMAP_SIZE);
					const col = idx % HEATMAP_SIZE;
					const level = HEATMAP_DATA[row]?.[col] ?? 0;
					return (
						<div
							key={`hm-${row}-${col}`}
							data-heatmap-cell=""
							className="h-8 w-8 rounded-sm"
							style={{ backgroundColor: `var(--color-heatmap-${level})` }}
							aria-label={`相关度 ${row + 1}-${col + 1}: 等级${level}`}
						/>
					);
				})}
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
