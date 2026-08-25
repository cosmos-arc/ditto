import { StatusBadge } from "@/components/status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

function percent(value: number | null, digits = 2): string {
	return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function RiskAlert({ title, detail }: { readonly title: string; readonly detail: string }) {
	return (
		<div
			role="alert"
			className="rounded-(--radius-sm) border border-(--color-risk-critical-fg) bg-(--color-risk-critical-bg) p-3"
		>
			<p className="text-sm font-medium text-(--color-risk-critical-fg)">{title}</p>
			<p className="mt-1 text-xs text-(--color-foreground-secondary)">{detail}</p>
		</div>
	);
}

export function RiskDecisionCenter({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const reconciliationMatched = ["matched", "reconciled", "ok"].includes(decision.reconciliation.status.toLowerCase());
	const tailRiskUnavailable = [decision.tailRisk.historicalEs99, decision.tailRisk.historicalVar99].every(
		(value) => value == null,
	);

	return (
		<section data-slot="risk-decision-center" className="flex flex-col gap-(--section-gap)">
			<Panel data-slot="risk-tail">
				<PanelHeader
					title="尾部风险"
					subtitle={
						decision.tailRisk.monteCarloSeed == null
							? undefined
							: `Monte Carlo seed: ${decision.tailRisk.monteCarloSeed}`
					}
				/>
				<PanelBody className="grid grid-cols-2 gap-3 p-3 lg:grid-cols-4">
					{tailRiskUnavailable && (
						<div className="col-span-full">
							<RiskAlert title="尾部风险不可用" detail="Historical ES99/VaR99 均缺失，决策保持 fail-closed。" />
						</div>
					)}
					{[
						["Historical ES99", decision.tailRisk.historicalEs99],
						["Historical VaR99", decision.tailRisk.historicalVar99],
						["Parametric VaR99", decision.tailRisk.parametricVar99],
						["Monte Carlo VaR99", decision.tailRisk.monteCarloVar99],
					].map(([label, value]) => (
						<div key={String(label)} className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
							<p className="text-xs text-(--color-foreground-tertiary)">{label}</p>
							<p className="mt-1 font-data text-lg tabular-nums text-(--color-foreground)">
								{percent(value as number | null)}
							</p>
						</div>
					))}
				</PanelBody>
			</Panel>

			<Panel data-slot="risk-factor">
				<PanelHeader
					title="因子风险贡献"
					actions={
						<StatusBadge
							label={decision.factorRisk.availability}
							variant={decision.factorRisk.availability === "available" ? "healthy" : "critical"}
						/>
					}
				/>
				<PanelBody className="flex flex-col gap-3 p-3">
					{decision.factorRisk.availability === "unavailable" ? (
						<RiskAlert title="因子风险不可用" detail="未返回可验证的因子贡献，决策保持 fail-closed。" />
					) : (
						<>
							<dl className="grid grid-cols-2 gap-3 text-xs">
								<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
									<dt className="text-(--color-foreground-tertiary)">总风险</dt>
									<dd className="mt-1 font-data text-lg tabular-nums text-(--color-foreground)">
										{percent(decision.factorRisk.totalRisk)}
									</dd>
								</div>
								<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
									<dt className="text-(--color-foreground-tertiary)">Euler residual</dt>
									<dd className="mt-1 font-data text-lg tabular-nums text-(--color-foreground)">
										{percent(decision.factorRisk.eulerResidual, 4)}
									</dd>
								</div>
							</dl>
							<div className="overflow-x-auto">
								<table className="w-full min-w-120 text-left text-sm">
									<thead className="text-xs text-(--color-foreground-tertiary)">
										<tr>
											<th className="px-3 py-2 font-medium">factor</th>
											<th className="px-3 py-2 font-medium">marginal</th>
											<th className="px-3 py-2 font-medium">contribution</th>
										</tr>
									</thead>
									<tbody className="divide-y divide-(--color-border-subtle)">
										{Object.entries(decision.factorRisk.percentageContributions).map(([factor, contribution]) => (
											<tr key={factor}>
												<td className="px-3 py-2 font-data text-(--color-foreground)">{factor}</td>
												<td className="px-3 py-2 font-data tabular-nums">
													{percent(decision.factorRisk.marginalContributions[factor] ?? null)}
												</td>
												<td className="px-3 py-2 font-data tabular-nums">{percent(contribution)}</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						</>
					)}
				</PanelBody>
			</Panel>

			<Panel data-slot="risk-stress">
				<PanelHeader title="压力场景" subtitle={decision.stressTests.catalogVersion} />
				<PanelBody className="flex flex-col gap-3 p-3">
					{decision.stressTests.unavailableScenarios.map((scenario) => (
						<RiskAlert key={scenario} title={`场景不可用：${scenario}`} detail="场景损失未生成，不以零损失替代。" />
					))}
					<div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
						{Object.entries(decision.stressTests.losses).map(([scenario, loss]) => (
							<div key={scenario} className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
								<p className="font-data text-sm text-(--color-foreground)">{scenario}</p>
								<p className="mt-1 font-data text-lg tabular-nums text-(--color-risk-critical-fg)">{percent(loss)}</p>
							</div>
						))}
					</div>
				</PanelBody>
			</Panel>

			<div className="grid gap-(--section-gap) lg:grid-cols-2">
				{reconciliationMatched ? (
					<Panel>
						<PanelHeader title="对账" actions={<StatusBadge label="对账一致" variant="healthy" />} />
						<PanelBody className="p-3 text-xs text-(--color-foreground-secondary)">
							账户、持仓与决策基线一致。
						</PanelBody>
					</Panel>
				) : (
					<RiskAlert
						title="对账不一致"
						detail={`${decision.reconciliation.differences.join("、") || "未返回差异明细"}${
							decision.reconciliation.alertIdempotencyKey
								? ` · alert ${decision.reconciliation.alertIdempotencyKey}`
								: ""
						}`}
					/>
				)}

				{decision.provenance.complete ? (
					<Panel>
						<PanelHeader title="PIT provenance" actions={<StatusBadge label="完整" variant="healthy" />} />
						<PanelBody className="grid gap-3 p-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
							<div>
								<p className="text-(--color-foreground-tertiary)">decision time</p>
								<p className="mt-1 font-data text-(--color-foreground)">{decision.provenance.decisionTime ?? "—"}</p>
							</div>
							<div>
								<p className="text-(--color-foreground-tertiary)">knowledge cutoff</p>
								<p className="mt-1 font-data text-(--color-foreground)">{decision.provenance.knowledgeCutoff ?? "—"}</p>
							</div>
							<div>
								<p className="text-(--color-foreground-tertiary)">publication cutoff</p>
								<p className="mt-1 font-data text-(--color-foreground)">
									{decision.provenance.publicationCutoff ?? "—"}
								</p>
							</div>
							<div>
								<p className="text-(--color-foreground-tertiary)">generated at</p>
								<p className="mt-1 font-data text-(--color-foreground)">{decision.provenance.generatedAt ?? "—"}</p>
							</div>
							<div className="sm:col-span-2">
								<p className="text-(--color-foreground-tertiary)">source snapshots</p>
								<p className="mt-1 break-all font-data text-(--color-foreground)">
									{decision.provenance.sourceSnapshotIds.join(" · ") || "—"}
								</p>
							</div>
						</PanelBody>
					</Panel>
				) : (
					<RiskAlert title="PIT provenance 不完整" detail="cutoff 或 source snapshot 缺失，风险结论不可用于执行。" />
				)}
			</div>
		</section>
	);
}
