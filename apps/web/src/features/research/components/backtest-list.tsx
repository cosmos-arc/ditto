import type { BacktestRun } from "../types";

const MOCK_RUNS: BacktestRun[] = [
	{ id: "#RUN-0942", strategy: "Momentum_Arbitrage_v4.2", time: "2h ago", sharpe: 2.41, maxDrawdown: 8.2 },
	{ id: "#RUN-0938", strategy: "Mean_Rev_Scalper_Test", time: "5h ago", sharpe: 1.14, maxDrawdown: 14.1 },
	{ id: "#RUN-0912", strategy: "X-Modal_Sentiment_HFT", time: "Yesterday", sharpe: 3.08, maxDrawdown: 4.5, dimmed: true },
];

function MetricTile({ label, value, color }: { readonly label: string; readonly value: string; readonly color?: string }) {
	return (
		<div className="rounded bg-surface-app/50 p-1.5 text-center">
			<div className="text-[10px] uppercase text-text-secondary">{label}</div>
			<div className={`text-sm font-mono font-bold tabular-nums ${color ?? "text-text-primary"}`}>
				{value}
			</div>
		</div>
	);
}

export function BacktestList() {
	return (
		<div className="flex max-h-150 flex-col overflow-hidden rounded-xl border border-outline/30 bg-surface-panel shadow-sm">
			<div className="flex items-center justify-between border-b border-outline/30 bg-surface-canvas px-4 py-3">
				<span className="text-sm font-bold tracking-tight">Recent Backtests</span>
				<span className="material-symbols-outlined text-text-secondary">history</span>
			</div>

			<div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto p-4">
				{MOCK_RUNS.map((run) => (
					<div
						key={run.id}
						className={`cursor-pointer rounded-lg border border-outline/20 bg-surface-elevated p-3 transition-colors hover:border-blue-600/50 group ${run.dimmed ? "opacity-60" : ""}`}
					>
						<div className="mb-2 flex items-center justify-between">
							<span className="text-[10px] font-mono uppercase text-blue-700">
								{run.id}
							</span>
							<span className="text-[10px] text-text-secondary">{run.time}</span>
						</div>
						<div className="mb-3 text-xs font-semibold group-hover:text-blue-700 transition-colors">
							{run.strategy}
						</div>
						<div className="grid grid-cols-2 gap-2">
							<MetricTile
								label="Sharpe"
								value={run.sharpe.toFixed(2)}
								color={run.sharpe >= 2 ? "text-green-500" : undefined}
							/>
							<MetricTile
								label="Max DD"
								value={`${run.maxDrawdown.toFixed(1)}%`}
								color={run.maxDrawdown >= 12 ? "text-red-500" : undefined}
							/>
						</div>
					</div>
				))}
			</div>

			<button
				type="button"
				className="flex w-full items-center justify-center gap-1 border-t border-outline/30 p-3 text-[11px] font-bold text-text-secondary transition-colors hover:text-text-primary"
			>
				View All Runs
				<span className="material-symbols-outlined text-sm">arrow_forward</span>
			</button>
		</div>
	);
}
