import { ContextSection } from "@/components/domain/context-section";
import type { ExperimentPreflight } from "../api/experiments";

interface ExperimentPreflightPanelProps {
	readonly preflight: ExperimentPreflight | null;
	readonly isStale: boolean;
	readonly confirmed: boolean;
	readonly onConfirmedChange: (confirmed: boolean) => void;
}

function Metric({ label, value }: { readonly label: string; readonly value: string }) {
	return (
		<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2">
			<span className="block text-xs text-(--color-foreground-tertiary)">{label}</span>
			<strong className="font-data text-sm">{value}</strong>
		</div>
	);
}

export function ExperimentPreflightPanel({
	preflight,
	isStale,
	confirmed,
	onConfirmedChange,
}: ExperimentPreflightPanelProps) {
	return (
		<ContextSection title="Server preflight">
			{!preflight ? (
				<p className="p-(--density-panel-padding) text-sm text-(--color-foreground-tertiary)">
					尚未运行。Preflight 为只读，不创建 experiment。
				</p>
			) : (
				<div className="flex flex-col gap-3 p-(--density-panel-padding)">
					{isStale && (
						<p role="status" className="text-sm text-(--color-led-warning)">
							Preflight 已过期
						</p>
					)}
					<div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
						<Metric label="Status" value={preflight.status} />
						<Metric label="Candidates" value={String(preflight.candidateCount)} />
						<Metric label="Eligible history" value={`${preflight.eligibleMonthCount} 个月`} />
						<Metric label="Isolation width" value={`${preflight.isolationWidthSessions} sessions`} />
						<Metric label="Folds" value={String(preflight.plannedFoldCount)} />
						<Metric label="Budget runs" value={String(preflight.budgetRunCount)} />
						<Metric label="Trading sessions" value={String(preflight.estimatedTradingSessions)} />
						<Metric label="Estimated disk" value={`${preflight.estimatedDiskBytes} bytes`} />
					</div>
					<div className="divide-y divide-(--color-border-subtle) border-y border-(--color-border-subtle)">
						{preflight.checks.map((check) => (
							<div key={check.ruleId} className="grid gap-1 py-2 text-xs xl:grid-cols-[12rem_5rem_1fr_1fr]">
								<span className="font-data">{check.ruleId}</span>
								<span>{check.outcome}</span>
								<code className="break-all">observed {JSON.stringify(check.observed)}</code>
								<code className="break-all">policy {JSON.stringify(check.policy)}</code>
								{check.reason && <p>{check.reason}</p>}
								{check.remediation && <p>{check.remediation}</p>}
							</div>
						))}
					</div>
					<label className="flex items-start gap-2 text-sm">
						<input
							type="checkbox"
							checked={confirmed && !isStale}
							disabled={isStale || !preflight.planHash || preflight.status.toLowerCase() !== "ready"}
							onChange={(event) => onConfirmedChange(event.target.checked)}
							aria-label={`确认 plan hash ${preflight.planHash ?? "unavailable"}`}
						/>
						<span className="min-w-0">
							确认 plan hash <code className="break-all">{preflight.planHash ?? "unavailable"}</code>
						</span>
					</label>
				</div>
			)}
		</ContextSection>
	);
}
