import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { RegimeDiagnostics, RegimeLabel, RegimeObservation } from "../api/regime-diagnostics";

const LABEL_META: Record<
	RegimeLabel,
	{ readonly code: string; readonly title: string; readonly badge: "regime-on" | "regime-off" | "regime-mixed" }
> = {
	bull: { code: "BULL", title: "风险偏好", badge: "regime-on" },
	bear: { code: "BEAR", title: "风险规避", badge: "regime-off" },
	neutral: { code: "NEUTRAL", title: "中性区间", badge: "regime-mixed" },
};

export function regimeLabelMeta(label: RegimeLabel) {
	return LABEL_META[label];
}

function clampScore(score: number): number {
	return Math.max(0, Math.min(100, score));
}

function ScoreRuler({ diagnostics }: { readonly diagnostics: RegimeDiagnostics }) {
	const { bearThreshold, bullThreshold, current } = diagnostics;
	const score = clampScore(current.score);
	return (
		<div className="mt-5">
			<div className="h-12 overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle)">
				<svg viewBox="0 0 100 48" preserveAspectRatio="none" className="h-full w-full" aria-hidden="true">
					<rect x="0" y="0" width={bearThreshold} height="48" fill="var(--color-market-down-bg)" />
					<rect
						x={bearThreshold}
						y="0"
						width={bullThreshold - bearThreshold}
						height="48"
						fill="var(--color-surface-strip)"
					/>
					<rect x={bullThreshold} y="0" width={100 - bullThreshold} height="48" fill="var(--color-market-up-bg)" />
					<line
						x1={bearThreshold}
						x2={bearThreshold}
						y1="0"
						y2="48"
						stroke="var(--color-border-strong)"
						vectorEffect="non-scaling-stroke"
					/>
					<line
						x1={bullThreshold}
						x2={bullThreshold}
						y1="0"
						y2="48"
						stroke="var(--color-border-strong)"
						vectorEffect="non-scaling-stroke"
					/>
					<line
						x1={score}
						x2={score}
						y1="4"
						y2="44"
						stroke="var(--color-accent)"
						strokeWidth="2"
						vectorEffect="non-scaling-stroke"
					/>
				</svg>
			</div>
			<div className="mt-1.5 grid grid-cols-3 text-xs text-(--color-foreground-tertiary)">
				<span>BEAR · &lt; {bearThreshold.toFixed(0)}</span>
				<span className="text-center">NEUTRAL</span>
				<span className="text-right">BULL · ≥ {bullThreshold.toFixed(0)}</span>
			</div>
		</div>
	);
}

function timelinePoints(observations: readonly RegimeObservation[]): string {
	if (observations.length === 0) return "";
	if (observations.length === 1) return `20,${170 - clampScore(observations[0]?.score ?? 0) * 1.4}`;
	return observations
		.map((observation, index) => {
			const x = 20 + (index / (observations.length - 1)) * 680;
			const y = 160 - clampScore(observation.score) * 1.3;
			return `${x.toFixed(1)},${y.toFixed(1)}`;
		})
		.join(" ");
}

function RegimeTimeline({ diagnostics }: { readonly diagnostics: RegimeDiagnostics }) {
	const observations = diagnostics.observations;
	const latest = observations.slice(-7);
	return (
		<Panel className="min-h-72 flex-1">
			<PanelHeader
				title="Regime Timeline"
				subtitle={`${diagnostics.scope.startDate} → ${diagnostics.scope.endDate}`}
				count={observations.length}
			/>
			<PanelBody className="p-3">
				{observations.length === 0 ? (
					<div className="flex h-full min-h-48 items-center justify-center text-xs text-(--color-foreground-tertiary)">
						该范围没有可见观测，未评估
					</div>
				) : (
					<>
						<div className="relative h-44 overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-app)">
							<div className="absolute inset-x-0 top-0 h-[35%] bg-(--color-market-up-bg)" />
							<div className="absolute inset-x-0 top-[35%] h-[30%] bg-(--color-surface-strip)" />
							<div className="absolute inset-x-0 bottom-0 h-[35%] bg-(--color-market-down-bg)" />
							<svg
								viewBox="0 0 720 180"
								className="absolute inset-0 h-full w-full"
								role="img"
								aria-label="Regime 评分时序"
							>
								<title>Regime 评分时序</title>
								<line
									x1="0"
									x2="720"
									y1={160 - diagnostics.bullThreshold * 1.3}
									y2={160 - diagnostics.bullThreshold * 1.3}
									className="stroke-(--color-border-strong)"
									strokeDasharray="4 4"
								/>
								<line
									x1="0"
									x2="720"
									y1={160 - diagnostics.bearThreshold * 1.3}
									y2={160 - diagnostics.bearThreshold * 1.3}
									className="stroke-(--color-border-strong)"
									strokeDasharray="4 4"
								/>
								<polyline
									points={timelinePoints(observations)}
									className="fill-none stroke-(--color-accent)"
									strokeWidth="2.5"
									strokeLinejoin="round"
									strokeLinecap="round"
								/>
							</svg>
							<div className="absolute top-2 right-2 flex flex-col items-end gap-1 text-[9px] font-data text-(--color-foreground-tertiary)">
								<span>BULL</span>
								<span className="mt-8">NEUTRAL</span>
								<span className="mt-8">BEAR</span>
							</div>
						</div>
						<div className="mt-3 overflow-x-auto">
							<table className="w-full text-left text-xs" aria-label="最近 Regime 观测">
								<thead className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">
									<tr>
										<th className="pb-2 font-medium">观测日</th>
										<th className="pb-2 font-medium">状态</th>
										<th className="pb-2 text-right font-medium">评分</th>
										<th className="pb-2 text-right font-medium">模型映射</th>
									</tr>
								</thead>
								<tbody>
									{latest.toReversed().map((observation) => (
										<tr key={observation.observedAt} className="border-t border-(--color-border-subtle)">
											<td className="py-2 font-data text-(--color-foreground-secondary)">{observation.observedAt}</td>
											<td className="py-2">
												<StatusBadge
													size="sm"
													variant={LABEL_META[observation.label].badge}
													label={LABEL_META[observation.label].code}
												/>
											</td>
											<td className="py-2 text-right font-data tabular-nums">{observation.score.toFixed(1)}</td>
											<td className="py-2 text-right font-data tabular-nums text-(--color-foreground-secondary)">
												{(observation.positionRatio * 100).toFixed(0)}%
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					</>
				)}
			</PanelBody>
		</Panel>
	);
}

export function RegimeDiagnosticsView({ diagnostics }: { readonly diagnostics: RegimeDiagnostics }) {
	const label = LABEL_META[diagnostics.current.label];
	return (
		<div className="flex h-full min-h-0 flex-col gap-3">
			<div>
				<Panel>
					<PanelHeader title="Regime Indicator" subtitle="仅使用 cutoff 前可见的收盘观测" />
					<PanelBody className="grid min-h-44 gap-5 p-4 min-[900px]:grid-cols-[15rem_minmax(0,1fr)]">
						<div className="flex items-center gap-4 border-r border-(--color-border-subtle) pr-5 max-[899px]:border-r-0 max-[899px]:border-b max-[899px]:pb-4">
							<div className="flex size-24 shrink-0 flex-col items-center justify-center rounded-full border border-(--color-border-strong) bg-[radial-gradient(circle,var(--color-surface-panel-elevated),var(--color-surface-app))] shadow-[inset_0_0_0_8px_var(--color-surface-strip)]">
								<span className="font-data text-3xl font-semibold tabular-nums text-(--color-foreground)">
									{diagnostics.current.score.toFixed(1)}
								</span>
								<span className="text-[9px] uppercase tracking-[0.16em] text-(--color-foreground-tertiary)">
									score / 100
								</span>
							</div>
							<div className="min-w-0">
								<StatusBadge variant={label.badge} label={label.code} />
								<h2 className="mt-2 text-lg font-semibold text-(--color-foreground)">{label.title}</h2>
								<p className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">
									{diagnostics.current.observedAt}
								</p>
							</div>
						</div>
						<div className="min-w-0">
							<div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-(--color-foreground-secondary)">
								<span>
									模型{" "}
									<strong className="font-data font-medium text-(--color-foreground)">{diagnostics.modelId}</strong>
								</span>
								<span>
									Lookback{" "}
									<strong className="font-data font-medium text-(--color-foreground)">
										{diagnostics.lookbackObservations}
									</strong>
								</span>
								<span>
									模型映射{" "}
									<strong className="font-data font-medium text-(--color-foreground)">
										{(diagnostics.current.positionRatio * 100).toFixed(0)}%
									</strong>
								</span>
							</div>
							<ScoreRuler diagnostics={diagnostics} />
						</div>
					</PanelBody>
				</Panel>
			</div>
			<div className="min-h-0 flex-1">
				<RegimeTimeline diagnostics={diagnostics} />
			</div>
		</div>
	);
}
