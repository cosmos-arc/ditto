import { FactorHealthTable } from "./factor-health-table";
import { QuickActionGrid } from "./quick-action-grid";
import { BacktestList } from "./backtest-list";
import { ActiveExperiments } from "./active-experiments";

const FACTOR_CATEGORIES = [
	{ label: "All Factors", active: true },
	{ label: "Momentum", active: false },
	{ label: "Mean Reversion", active: false },
	{ label: "Sentiment", active: false },
	{ label: "Volume Profile", active: false },
] as const;

export function ResearchPage() {
	return (
		<div className="bg-dots p-density-padding">
			{/* Filter Bar */}
			<section className="mb-6 flex items-center justify-between rounded-lg border border-outline/30 bg-surface-panel/50 p-3 backdrop-blur-md">
				<div className="flex items-center gap-4">
					<span className="text-sm font-semibold text-text-secondary">Factor Categories:</span>
					<div className="flex gap-2">
					{FACTOR_CATEGORIES.map((cat) => (
						<button
							key={cat.label}
							type="button"
							className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
								cat.active
									? "bg-blue-500 text-on-primary-container"
									: "bg-surface-raised text-text-secondary hover:bg-outline/50"
							}`}
						>
							{cat.label}
						</button>
					))}
					</div>
				</div>
				<div className="flex items-center gap-2">
					<button
						type="button"
						className="flex items-center gap-1.5 rounded px-3 py-1 text-xs text-text-secondary transition-colors hover:bg-surface-raised hover:text-text-primary"
					>
						<span className="material-symbols-outlined text-sm">filter_list</span>
						Filter
					</button>
					<button
						type="button"
						className="flex items-center gap-1.5 rounded bg-blue-500 px-3 py-1 text-xs font-bold text-on-primary-container transition-opacity hover:opacity-90"
					>
						<span className="material-symbols-outlined text-sm">add</span>
						New Factor
					</button>
				</div>
			</section>

			{/* Main 12-col grid */}
			<div className="grid grid-cols-12 gap-density-section-gap">
				{/* Center: 9 cols */}
				<div className="col-span-12 space-y-density-section-gap lg:col-span-9">
					<FactorHealthTable />
					<QuickActionGrid />
				</div>

				{/* Right sidebar: 3 cols */}
				<aside className="col-span-12 space-y-density-section-gap lg:col-span-3">
					<BacktestList />
					<ActiveExperiments />
				</aside>
			</div>
		</div>
	);
}
