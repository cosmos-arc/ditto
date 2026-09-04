import type { components } from "@/types/generated/api";

interface ExperimentValidationViewProps {
	readonly folds: readonly components["schemas"]["ExperimentFoldResponse"][];
	readonly gates: readonly components["schemas"]["ExperimentGateResponse"][];
}

export function ExperimentValidationView({ folds, gates }: ExperimentValidationViewProps) {
	const partialFailure = folds.some((fold) => fold.status.toLowerCase() === "failed");
	return (
		<div className="flex flex-col gap-2">
			{partialFailure && <p className="text-xs text-(--color-led-warning)">partial fold failure</p>}
			<div className="overflow-x-auto rounded-(--radius-sm) border border-(--color-border-subtle)">
				<table className="w-full border-collapse text-left text-xs" aria-label="Fold validation">
					<thead>
						<tr className="bg-(--color-surface-strip) text-xs uppercase tracking-[0.06em] text-(--color-foreground-tertiary)">
							<th className="px-3 py-2">Fold</th>
							<th className="px-3 py-2">Status</th>
							<th className="px-3 py-2">Window</th>
							<th className="px-3 py-2">Purge / embargo</th>
						</tr>
					</thead>
					<tbody>
						{folds.map((fold) => (
							<tr key={`${fold.candidate_id}:${fold.fold_id}`} className="border-t border-(--color-border-subtle)">
								<td className="px-3 py-2 font-data font-medium">{fold.fold_id}</td>
								<td className="px-3 py-2">{fold.status}</td>
								<td className="px-3 py-2 font-data">
									{fold.test_start} → {fold.test_end}
								</td>
								<td className="px-3 py-2 font-data">
									{fold.purge_sessions} / {fold.embargo_sessions}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
			<div className="overflow-hidden rounded-(--radius-sm) border border-(--color-border-subtle)">
				{gates.map((gate) => (
					<div
						key={gate.evaluation_id}
						className="grid gap-2 border-b border-(--color-border-subtle) px-3 py-2 text-xs last:border-b-0 sm:grid-cols-[12rem_5rem_1fr]"
					>
						<strong className="font-data">{gate.rule_id}</strong>
						<span className="font-medium">{gate.outcome}</span>
						<code className="break-all text-(--color-foreground-secondary)">
							{JSON.stringify({ observed: gate.observed, policy: gate.policy })}
						</code>
					</div>
				))}
				{gates.length === 0 && (
					<p className="px-3 py-4 text-xs text-(--color-foreground-tertiary)">尚未发布 gate evaluation。</p>
				)}
			</div>
		</div>
	);
}
