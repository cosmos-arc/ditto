import { StatusBadge, getIcColor } from "./status-badge";
import type { Factor } from "../types";

const MOCK_FACTORS: Factor[] = [
	{ name: "Alpha_EMA_Cross_V1", category: "Momentum", ic: 0.042, ir: 1.28, decay: -2.4, status: "stable" },
	{ name: "Vol_Dispersion_30m", category: "Volatility", ic: 0.038, ir: 0.94, decay: -1.1, status: "stable" },
	{ name: "NLP_Sentiment_Lag3", category: "Sentiment", ic: 0.012, ir: 0.45, decay: -18.4, status: "decay" },
	{ name: "Orderbook_Imbalance_1s", category: "Microstructure", ic: 0.081, ir: 2.14, decay: -0.2, status: "optimal" },
	{ name: "Whale_Flow_Index", category: "Flow", ic: -0.004, ir: 0.11, decay: -42.8, status: "failed" },
	{ name: "Mean_Rev_Bollinger_4h", category: "Mean Rev", ic: 0.029, ir: 0.82, decay: -3.5, status: "stable" },
];

const STATUS_LABELS: Record<string, string> = {
	stable: "STABLE",
	optimal: "OPTIMAL",
	decay: "DECAY",
	failed: "FAILED",
};

export function FactorHealthTable() {
	return (
		<div className="overflow-hidden rounded-xl border border-outline/30 bg-surface-panel shadow-sm">
			{/* 表头 */}
			<div className="flex items-center justify-between border-b border-outline/30 bg-surface-canvas px-4 py-3">
				<div className="flex items-center gap-2">
					<span className="material-symbols-outlined text-blue-700">health_metrics</span>
					<span className="text-sm font-bold tracking-tight">因子健康监控</span>
				</div>
				<div className="flex items-center gap-4 text-[11px] text-text-secondary">
					<span className="flex items-center gap-1">
						<span className="inline-block size-2 rounded-full bg-green-500" />
						<span>24 Optimal</span>
					</span>
					<span className="flex items-center gap-1">
						<span className="inline-block size-2 rounded-full bg-amber-500" />
						<span>3 Decaying</span>
					</span>
					<span className="flex items-center gap-1">
						<span className="inline-block size-2 rounded-full bg-red-500" />
						<span>1 Failed</span>
					</span>
				</div>
			</div>

			{/* 表格 */}
			<div className="overflow-x-auto">
				<table className="w-full border-collapse">
					<thead>
						<tr className="bg-surface-elevated/50 text-left text-[11px] font-semibold uppercase tracking-wider text-text-secondary">
							<th className="border-b border-outline/30 px-4 py-2">Factor Name</th>
							<th className="border-b border-outline/30 px-4 py-2">Category</th>
							<th className="border-b border-outline/30 px-4 py-2 text-right">IC (Mean)</th>
							<th className="border-b border-outline/30 px-4 py-2 text-right">IR</th>
							<th className="border-b border-outline/30 px-4 py-2 text-right">Decay (T+1)</th>
							<th className="border-b border-outline/30 px-4 py-2 text-center">Status</th>
						</tr>
					</thead>
					<tbody className="divide-y divide-outline/20 font-mono text-xs">
						{MOCK_FACTORS.map((factor) => (
							<tr
								key={factor.name}
								className="cursor-pointer transition-colors hover:bg-surface-elevated"
							>
								<td className="px-4 py-3 font-medium text-text-primary">
									{factor.name}
								</td>
								<td className="px-4 py-3 text-text-secondary">{factor.category}</td>
								<td className={`px-4 py-3 text-right tabular-nums ${getIcColor(factor.ic)}`}>
									{factor.ic.toFixed(3)}
								</td>
								<td className="px-4 py-3 text-right tabular-nums text-text-primary">
									{factor.ir.toFixed(2)}
								</td>
								<td className={`px-4 py-3 text-right tabular-nums ${factor.decay < -10 ? "text-amber-500" : factor.decay < -5 ? "text-text-secondary" : "text-text-primary"}`}>
									{factor.decay > 0 ? "+" : ""}
									{factor.decay.toFixed(1)}%
								</td>
								<td className="px-4 py-3 text-center">
									<StatusBadge
										status={factor.status}
										label={STATUS_LABELS[factor.status]}
									/>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>

			{/* 表尾 */}
			<div className="flex items-center justify-between border-t border-outline/30 bg-surface-canvas px-4 py-2 text-[10px]">
				<span className="text-text-muted">Showing 6 of 28 factors active in research</span>
				<button
					type="button"
					className="font-bold uppercase tracking-wider text-blue-700 transition-colors hover:underline"
				>
					Expand Monitor
				</button>
			</div>
		</div>
	);
}
