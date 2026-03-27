const ACTIONS = [
	{
		icon: "add_task",
		title: "New Backtest",
		description: "Launch multi-threaded simulation",
		iconBg: "bg-blue-500/20",
		iconColor: "text-blue-700",
	},
	{
		icon: "analytics",
		title: "Factor Analysis",
		description: "IC Decay & Collinearity checks",
		iconBg: "bg-cyan-500/20",
		iconColor: "text-cyan-700",
	},
	{
		icon: "tune",
		title: "Strategy Config",
		description: "Manage weights and risk limits",
		iconBg: "bg-orange-500/20",
		iconColor: "text-orange-700",
	},
] as const;

export function QuickActionGrid() {
	return (
		<div className="grid grid-cols-3 gap-6">
			{ACTIONS.map((action) => (
				<button
					key={action.title}
					type="button"
					className="flex items-center gap-4 cursor-pointer rounded-xl border border-outline/20 bg-surface-panel p-4 text-left shadow-sm transition-all hover:border-blue-600/50 hover:shadow-md group"
				>
					<div
						className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${action.iconBg} transition-transform group-hover:scale-110`}
					>
						<span className={`material-symbols-outlined ${action.iconColor}`}>
							{action.icon}
						</span>
					</div>
					<div>
						<h3 className="text-xs font-bold text-text-primary">{action.title}</h3>
						<p className="text-[10px] text-text-secondary">{action.description}</p>
					</div>
				</button>
			))}
		</div>
	);
}
