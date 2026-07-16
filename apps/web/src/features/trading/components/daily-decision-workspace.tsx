import { StatusBadge } from "@/components/status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { components } from "@/types/generated/api";

type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type DailyDecisionAction = components["schemas"]["DailyDecisionActionResponse"];
type GeneratedReasonCode = DailyDecisionV2Response["readiness"]["reason_codes"][number];
type ReasonCode = GeneratedReasonCode | "EOD_RUN_INCOMPLETE" | "SIGNAL_INTENT_MISMATCH";

const RECOVERY_LABEL: Record<ReasonCode, string> = {
	NO_ACTIVE_STRATEGY: "初始化并发布 seed 策略",
	REQUIRED_DATA_NOT_READY: "修复数据 freshness / DQ 后重跑 EOD",
	ACCOUNT_BASELINE_MISSING: "选择账户并导入完整账户基线",
	EOD_RUN_MISSING: "运行 EOD",
	EOD_RUN_FAILED: "查看运行日志并重跑 EOD",
	EOD_RUN_INCOMPLETE: "检查不完整的 EOD 证据并安全重跑",
	SIGNAL_PACKAGE_MISSING: "重新生成 signal package",
	SIGNAL_INTENT_MISMATCH: "停止交易并核对 package 与 intent 一致性",
	CHECKSUM_MISMATCH: "停止交易并核对 package 完整性",
	NO_REBALANCE_REQUIRED: "复核零调仓证据",
	RISK_WARNING: "复核风险证据",
	TRADE_DATE_MISMATCH: "核对实际成交日与建议交易日",
	RERUN_CONFLICT: "停止覆盖并人工处置重跑冲突",
	FILL_QUANTITY_EXCEEDED: "停止交易并核对成交数量与意图上限",
	QUANTITY_UNAVAILABLE: "补齐参考价与 sizing 证据",
	READY_FOR_REVIEW: "进入人工复核",
};

function percent(value: number, signed = false): string {
	const prefix = signed && value > 0 ? "+" : "";
	return `${prefix}${(value * 100).toFixed(2)}%`;
}

function quantity(value: number | null | undefined): string {
	return value == null ? "—" : value.toLocaleString("en-US");
}

function price(value: number | null | undefined): string {
	return value == null ? "—" : `¥${value.toFixed(2)}`;
}

function money(value: number | null | undefined): string {
	if (value == null) return "—";
	const sign = value < 0 ? "-" : "";
	return `${sign}¥${Math.abs(value).toLocaleString("en-US")}`;
}

function valueOrDash(value: string | null | undefined): string {
	return value?.trim() ? value : "—";
}

function eodCommand(report: DailyDecisionV2Response): string {
	const signalDate = report.identity.signal_date ?? "<signal_date>";
	const accountId = report.identity.account_id ?? "<account_id>";
	return [
		"pixi run -e dev ditto ops run-eod",
		`--signal-date ${signalDate}`,
		`--strategy-id ${report.identity.strategy_id}`,
		`--account-id ${accountId}`,
	].join(" ");
}

function recoveryCommand(reason: ReasonCode, report: DailyDecisionV2Response): string | null {
	if (reason === "NO_ACTIVE_STRATEGY") {
		return "pixi run -e dev ditto strategy bootstrap-seeds";
	}
	if (
		reason === "EOD_RUN_MISSING" ||
		reason === "EOD_RUN_FAILED" ||
		reason === "EOD_RUN_INCOMPLETE" ||
		reason === "SIGNAL_PACKAGE_MISSING" ||
		reason === "REQUIRED_DATA_NOT_READY" ||
		reason === "QUANTITY_UNAVAILABLE"
	) {
		return eodCommand(report);
	}
	return null;
}

function BlockedDecision({ report }: { readonly report: DailyDecisionV2Response }) {
	const reasons = report.readiness.reason_codes as readonly ReasonCode[];
	return (
		<div
			role="alert"
			className="flex flex-col gap-3 rounded-(--radius-sm) border border-(--color-risk-critical-fg) bg-(--color-risk-critical-bg) px-3 py-3"
		>
			<div>
				<p className="text-sm font-semibold text-(--color-foreground)">当前不可执行</p>
				<p className="mt-1 text-xs text-(--color-foreground-secondary)">交易动作保持关闭；先按后端证据完成恢复。</p>
			</div>
			{reasons.length === 0 ? (
				<p className="text-sm text-(--color-risk-critical-fg)">readiness 未返回 reason code，契约不完整，保持阻塞。</p>
			) : (
				<ul className="flex flex-col gap-3">
					{reasons.map((reason, index) => {
						const command = recoveryCommand(reason, report);
						return (
							<li key={reason} className="rounded-(--radius-sm) bg-(--color-surface-1) p-2">
								<div className="flex flex-wrap items-center gap-2">
									<code className="break-all font-data text-xs text-(--color-risk-critical-fg)">{reason}</code>
									<span className="text-sm text-(--color-foreground)">{RECOVERY_LABEL[reason]}</span>
								</div>
								{report.readiness.details?.[index] && (
									<p className="mt-1 text-xs text-(--color-foreground-secondary)">{report.readiness.details[index]}</p>
								)}
								{reason === "ACCOUNT_BASELINE_MISSING" && (
									<a
										href="#trading-execution-scope"
										className="mt-2 inline-flex text-xs font-medium text-(--color-accent) underline-offset-2 hover:underline"
									>
										前往执行范围
									</a>
								)}
								{command && (
									<code
										// biome-ignore lint/a11y/noNoninteractiveTabindex: Long recovery commands must be keyboard-focusable when they overflow on narrow screens.
										tabIndex={0}
										className="mt-2 block overflow-x-auto whitespace-nowrap rounded-(--radius-sm) bg-(--color-surface-inset) px-2 py-1.5 font-data text-xs text-(--color-foreground) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-focus-ring)"
									>
										{command}
									</code>
								)}
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);
}

function DecisionIdentity({ report }: { readonly report: DailyDecisionV2Response }) {
	const { identity } = report;
	return (
		<Panel>
			<PanelHeader title="D → D+1 决策链路" />
			<PanelBody className="p-3">
				<div className="grid gap-3 text-xs sm:grid-cols-3">
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<p className="text-(--color-foreground-tertiary)">D · 信号数据</p>
						<p className="mt-1 font-data text-sm text-(--color-foreground)">{valueOrDash(identity.signal_date)}</p>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<p className="text-(--color-foreground-tertiary)">决策生成</p>
						<p className="mt-1 font-data text-sm text-(--color-foreground)">{valueOrDash(identity.decision_date)}</p>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<p className="text-(--color-foreground-tertiary)">D+1 · 建议交易日</p>
						<p className="mt-1 font-data text-sm text-(--color-foreground)">
							{valueOrDash(identity.intended_trade_date)}
						</p>
					</div>
				</div>
				<div className="mt-3 grid gap-2 text-xs text-(--color-foreground-secondary) sm:grid-cols-2 lg:grid-cols-4">
					<span>策略 {identity.strategy_id}</span>
					<span>版本 {valueOrDash(identity.strategy_version)}</span>
					<span>账户 {valueOrDash(identity.account_id)}</span>
					<span>sleeve {valueOrDash(identity.sleeve_id)}</span>
				</div>
			</PanelBody>
		</Panel>
	);
}

function EvidencePanel({ report }: { readonly report: DailyDecisionV2Response }) {
	return (
		<Panel>
			<PanelHeader title="数据、运行与账户证据" count={report.data.dataset_states.length} />
			<PanelBody className="p-3">
				<div className="grid gap-3 lg:grid-cols-3">
					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
						<h3 className="text-xs font-medium text-(--color-foreground)">Dataset / DQ</h3>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
							freshness {report.data.freshness} · DQ {report.data.dq_state}
						</p>
						<ul className="mt-2 flex flex-col gap-2">
							{report.data.dataset_states.length === 0 ? (
								<li className="text-xs text-(--color-foreground-secondary)">未返回 dataset 证据</li>
							) : (
								report.data.dataset_states.map((dataset) => (
									<li key={dataset.dataset} className="text-xs">
										<div className="flex items-center justify-between gap-2">
											<span className="text-(--color-foreground)">{dataset.dataset}</span>
											<code className="font-data text-(--color-foreground-secondary)">{dataset.status}</code>
										</div>
										<p className="break-all font-data text-(--color-foreground-tertiary)">
											{valueOrDash(dataset.snapshot_id)}
										</p>
										{dataset.reason && <p className="text-(--color-risk-warning-fg)">{dataset.reason}</p>}
									</li>
								))
							)}
						</ul>
					</section>
					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3 text-xs">
						<h3 className="font-medium text-(--color-foreground)">Run / Package</h3>
						<dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-(--color-foreground-secondary)">
							<dt>outcome</dt>
							<dd className="font-data">{report.run_package.outcome}</dd>
							<dt>batch</dt>
							<dd className="break-all font-data">{valueOrDash(report.run_package.batch_key)}</dd>
							<dt>artifact</dt>
							<dd className="break-all font-data">{valueOrDash(report.run_package.artifact_id)}</dd>
							<dt>checksum</dt>
							<dd className="break-all font-data">{valueOrDash(report.run_package.checksum)}</dd>
							<dt>校验</dt>
							<dd>{report.run_package.checksum_valid ? "通过" : "失败"}</dd>
							<dt>风险证据</dt>
							<dd>{report.run_package.risk_evidence.join(", ") || "—"}</dd>
						</dl>
					</section>
					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3 text-xs">
						<h3 className="font-medium text-(--color-foreground)">Account Baseline</h3>
						<dl className="mt-2 grid grid-cols-2 gap-2 text-(--color-foreground-secondary)">
							<div>
								<dt>as-of</dt>
								<dd className="font-data">{valueOrDash(report.account_positions.as_of)}</dd>
							</div>
							<div>
								<dt>baseline</dt>
								<dd className="break-all font-data">{valueOrDash(report.account_positions.baseline_id)}</dd>
							</div>
							<div>
								<dt>可用现金</dt>
								<dd className="font-data">{money(report.account_positions.cash_available)}</dd>
							</div>
							<div>
								<dt>总资产</dt>
								<dd className="font-data">{money(report.account_positions.total_value)}</dd>
							</div>
							<div>
								<dt>敞口</dt>
								<dd className="font-data">{money(report.account_positions.exposure)}</dd>
							</div>
							<div>
								<dt>持仓</dt>
								<dd className="font-data">{report.account_positions.positions.length} 项</dd>
							</div>
						</dl>
					</section>
				</div>
			</PanelBody>
		</Panel>
	);
}

function ActionTable({ actions }: { readonly actions: readonly DailyDecisionAction[] }) {
	return (
		<section
			aria-label="执行建议表"
			// biome-ignore lint/a11y/noNoninteractiveTabindex: The wide execution table must be keyboard-focusable when it overflows on narrow screens.
			tabIndex={0}
			className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-focus-ring)"
		>
			<table className="w-full min-w-[76rem] border-collapse text-left text-xs">
				<thead className="text-(--color-foreground-tertiary)">
					<tr className="border-b border-(--color-border-subtle)">
						{[
							"标的 / 方向",
							"目标 / 当前 / 差额",
							"raw / rounded / lot",
							"建议 / 已成交 / 剩余",
							"参考价 / 现金影响",
							"Sizing 理由",
							"风险",
						].map((label) => (
							<th key={label} className="px-2 py-2 font-medium">
								{label}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{actions.map((action) => (
						<tr key={action.intent_id} className="border-b border-(--color-border-subtle) last:border-0">
							<td className="px-2 py-2">
								<div className="font-data text-(--color-foreground)">#{action.instrument_id}</div>
								<div className="uppercase text-(--color-foreground-tertiary)">{action.direction}</div>
							</td>
							<td className="px-2 py-2 font-data tabular-nums">
								{percent(action.target_weight)} / {percent(action.current_weight)} /{" "}
								{percent(action.delta_weight, true)}
							</td>
							<td className="px-2 py-2 font-data tabular-nums">
								{quantity(action.raw_quantity)} / {quantity(action.rounded_quantity)} / {quantity(action.lot_size)}
							</td>
							<td className="px-2 py-2 font-data tabular-nums">
								{quantity(action.suggested_quantity)} / {quantity(action.filled_quantity)} /{" "}
								{quantity(action.remaining_quantity)}
							</td>
							<td className="px-2 py-2 font-data tabular-nums">
								{price(action.reference_price)} / {money(action.cash_impact)}
							</td>
							<td className="max-w-48 break-words px-2 py-2 text-(--color-foreground-secondary)">
								{valueOrDash(action.reason)} · {valueOrDash(action.sizing_readiness)}
							</td>
							<td className="max-w-48 break-words px-2 py-2 text-(--color-foreground-secondary)">
								{action.risk_flags.join(", ") || "—"}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</section>
	);
}

function ExecutionReview({ report }: { readonly report: DailyDecisionV2Response }) {
	const review = report.execution_review;
	const actionsByIntent = new Map(report.actions.map((action) => [action.intent_id, action]));
	return (
		<Panel>
			<PanelHeader title="盘后复盘" count={review.effective_fills.length} />
			<PanelBody className="p-3">
				<div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
					<div className="flex flex-col gap-2">
						{review.effective_fills.length === 0 ? (
							<div className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-3 text-sm text-(--color-foreground-secondary)">
								尚无 effective fills
							</div>
						) : (
							review.effective_fills.map((fill) => {
								const remaining = actionsByIntent.get(fill.intent_id)?.remaining_quantity;
								return (
									<article
										key={fill.fill_id}
										className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-2 text-xs"
									>
										<div className="flex flex-wrap items-center justify-between gap-2">
											<span className="break-all font-data text-(--color-foreground)">{fill.fill_id}</span>
											<span className="font-data text-(--color-foreground-secondary)">剩余 {quantity(remaining)}</span>
										</div>
										<div className="mt-2 grid gap-1 text-(--color-foreground-secondary) sm:grid-cols-2 xl:grid-cols-4">
											<span>实际日 {fill.trade_date}</span>
											<span>
												{fill.direction.toUpperCase()} {quantity(fill.quantity)} @ {price(fill.fill_price)}
											</span>
											<span>
												费用 {money(fill.fee)} · 滑点 {fill.slippage}
											</span>
											<span>交收 {fill.settlement_date}</span>
										</div>
									</article>
								);
							})
						)}
						{review.deviation && (
							<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3 text-xs">
								<h3 className="font-medium text-(--color-foreground)">成交偏差</h3>
								<ul className="mt-2 grid gap-1 sm:grid-cols-2">
									{review.deviation.items.map((item) => (
										<li key={item.instrument_id} className="text-(--color-foreground-secondary)">
											#{item.instrument_id} · {item.fill_status} ·{" "}
											{item.deviation_bps == null ? "偏差 —" : `${item.deviation_bps} bps`}
										</li>
									))}
								</ul>
							</section>
						)}
					</div>
					<aside className="flex flex-col gap-3 rounded-(--radius-sm) bg-(--color-surface-1) px-3 py-3 text-xs">
						<div>
							<p className="text-(--color-foreground-tertiary)">Package checksum</p>
							<code className="mt-1 block break-all font-data text-(--color-foreground)">
								{valueOrDash(report.run_package.checksum)}
							</code>
						</div>
						<div>
							<p className="text-(--color-foreground-tertiary)">PnL</p>
							<p className="mt-1 font-data text-(--color-foreground)">
								{review.pnl ? `净盈亏 ${money(review.pnl.net_pnl)} · 费用 ${money(review.pnl.total_fees)}` : "净盈亏 —"}
							</p>
						</div>
						<div>
							<p className="text-(--color-foreground-tertiary)">异常 / 冲突</p>
							<ul className="mt-1 flex flex-col gap-1 font-data text-(--color-risk-warning-fg)">
								{[...review.exceptions, ...review.unresolved_conflicts].length === 0 ? (
									<li className="text-(--color-foreground-secondary)">无</li>
								) : (
									[...review.exceptions, ...review.unresolved_conflicts].map((item) => <li key={item}>{item}</li>)
								)}
							</ul>
						</div>
					</aside>
				</div>
			</PanelBody>
		</Panel>
	);
}

export function DailyDecisionWorkspace({ report }: { readonly report: DailyDecisionV2Response }) {
	const status = report.readiness.status;
	const reasons = report.readiness.reason_codes;
	return (
		<section className="flex flex-col gap-(--section-gap)" aria-label="Daily Decision 工作区">
			<DecisionIdentity report={report} />
			<EvidencePanel report={report} />
			<Panel>
				<PanelHeader title="今日决策" count={status === "blocked" ? 0 : report.actions.length} />
				<PanelBody className="p-3">
					<div className="mb-3 flex flex-wrap items-center gap-2">
						<StatusBadge
							label={status === "ready" ? "可执行" : status === "review" ? "需复核" : "阻塞"}
							variant={status === "ready" ? "healthy" : status === "review" ? "warning" : "critical"}
							size="sm"
						/>
						{reasons.map((reason) => (
							<code key={reason} className="break-all font-data text-xs text-(--color-foreground-tertiary)">
								{reason}
							</code>
						))}
					</div>
					{status === "blocked" ? (
						<BlockedDecision report={report} />
					) : report.actions.length === 0 ? (
						<div className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-4 text-sm text-(--color-foreground-secondary)">
							{report.run_package.no_rebalance ? "零调仓：本次决策无需执行交易。" : "暂无建议操作"}
						</div>
					) : (
						<ActionTable actions={report.actions} />
					)}
				</PanelBody>
			</Panel>
			{status !== "blocked" && <ExecutionReview report={report} />}
		</section>
	);
}
