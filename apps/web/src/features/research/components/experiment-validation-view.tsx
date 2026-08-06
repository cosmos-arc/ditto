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
			<div className="overflow-x-auto">
				<table className="w-full text-left text-xs">
					<thead>
						<tr>
							<th>Fold</th>
							<th>Status</th>
							<th>Window</th>
							<th>Purge / embargo</th>
						</tr>
					</thead>
					<tbody>
						{folds.map((fold) => (
							<tr key={`${fold.candidate_id}:${fold.fold_id}`}>
								<td>{fold.fold_id}</td>
								<td>{fold.status}</td>
								<td>
									{fold.test_start} → {fold.test_end}
								</td>
								<td>
									{fold.purge_sessions} / {fold.embargo_sessions}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
			<div className="divide-y divide-(--color-border-subtle)">
				{gates.map((gate) => (
					<div key={gate.evaluation_id} className="grid gap-1 py-2 text-xs sm:grid-cols-[12rem_5rem_1fr]">
						<strong>{gate.rule_id}</strong>
						<span>{gate.outcome}</span>
						<code>{JSON.stringify({ observed: gate.observed, policy: gate.policy })}</code>
					</div>
				))}
			</div>
		</div>
	);
}
