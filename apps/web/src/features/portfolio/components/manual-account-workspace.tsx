import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import {
	correctManualAccountEvent,
	createManualAccount,
	fetchManualAccountLedger,
	type ManualAccountEvent,
	type ManualAccountLedger,
	type ManualEventBody,
	recordManualAccountEvent,
	reverseManualAccountEvent,
} from "../api/manual-accounts";
import { tradingKeys } from "../api/query-keys";
import { AccountIdentityStrip } from "./account-identity-strip";
import { ManualAccountEventComposer } from "./manual-account-event-composer";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

const EVENT_LABELS: Readonly<Record<string, string>> = {
	opening_cash: "期初现金",
	opening_position: "期初持仓",
	buy: "买入",
	sell: "卖出",
	deposit: "资金存入",
	withdrawal: "资金取出",
	fee: "费用",
	tax: "税费",
	interest: "利息",
	dividend: "分红",
	transfer_in: "证券转入",
	transfer_out: "证券转出",
	split: "拆分",
	merge: "合并",
	other_corporate_action: "其他公司行动",
	reversal: "冲正",
	correction: "更正",
};

function formatMoney(value: string): string {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
}

function errorMessage(error: unknown): string {
	if (error instanceof ApiError) return error.detail ?? error.message;
	return error instanceof Error ? error.message : "账户操作失败";
}

function localIsoDate(): string {
	const now = new Date();
	const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
	return local.toISOString().slice(0, 10);
}

function Onboarding({
	asOf,
	onAccountSelected,
}: {
	readonly asOf: string;
	readonly onAccountSelected?: ((accountId: string) => void) | undefined;
}) {
	const [accountId, setAccountId] = useState("");
	const [name, setName] = useState("");
	const [openedAt, setOpenedAt] = useState(asOf);
	const [openingCash, setOpeningCash] = useState("");
	const [status, setStatus] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	async function create(): Promise<void> {
		if (!accountId.trim() || !name.trim() || !openedAt) return;
		setBusy(true);
		setStatus(null);
		try {
			const normalizedId = accountId.trim();
			await createManualAccount({
				account_id: normalizedId,
				currency: "CNY",
				name: name.trim(),
				opened_at: `${openedAt}T00:00:00+08:00`,
			});
			if (Number(openingCash) > 0) {
				await recordManualAccountEvent(normalizedId, {
					actor: "local-user",
					attachment_refs: [],
					event_type: "opening_cash",
					external_reference: null,
					fees: "0",
					gross_amount: openingCash,
					idempotency_key: `${normalizedId}:opening-cash:v1`,
					instrument_id: null,
					net_cash: null,
					note: "账户创建时录入的期初现金",
					price: "0",
					quantity: "0",
					settlement_date: openedAt,
					tax: "0",
					trade_date: openedAt,
				});
			}
			setStatus("账户已创建，期初现金已写入不可变账本");
			onAccountSelected?.(normalizedId);
		} catch (error) {
			setStatus(errorMessage(error));
		} finally {
			setBusy(false);
		}
	}

	return (
		<div className="min-h-full bg-(--color-surface-canvas)">
			<AccountIdentityStrip kind="manual" />
			<div className="mx-auto grid max-w-5xl gap-6 p-6 lg:grid-cols-[1fr_22rem]">
				<section className="rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-5">
					<p className="text-xs font-semibold tracking-[0.16em] text-(--color-status-healthy-fg)">MANUAL ACCOUNT</p>
					<h1 className="mt-2 text-xl font-semibold text-(--color-foreground)">创建我的实际账户记录</h1>
					<p className="mt-2 max-w-2xl text-sm leading-6 text-(--color-foreground-secondary)">
						这里只保存你确认的实际账户事实。Ditto 不连接券商，不会把 Manual 记录当成 Paper 成交，也不会替你下单。
					</p>
					<div className="mt-5 grid gap-3 sm:grid-cols-2">
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							账户 ID
							<input
								aria-label="账户 ID"
								className={INPUT_CLASS}
								value={accountId}
								onChange={(event) => setAccountId(event.currentTarget.value)}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							账户名称
							<input
								aria-label="账户名称"
								className={INPUT_CLASS}
								value={name}
								onChange={(event) => setName(event.currentTarget.value)}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							开户日期
							<input
								aria-label="开户日期"
								type="date"
								className={INPUT_CLASS}
								value={openedAt}
								onChange={(event) => setOpenedAt(event.currentTarget.value)}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							期初现金
							<input
								aria-label="期初现金"
								inputMode="decimal"
								className={INPUT_CLASS}
								value={openingCash}
								onChange={(event) => setOpeningCash(event.currentTarget.value)}
							/>
						</label>
					</div>
					<div className="mt-5 flex items-center gap-3">
						<Button
							type="button"
							disabled={busy || !accountId.trim() || !name.trim() || !openedAt}
							onClick={() => void create()}
						>
							{busy ? "创建并入账中…" : "创建 MANUAL 账户并入账"}
						</Button>
						{status && (
							<span role="status" className="text-xs text-(--color-foreground-secondary)">
								{status}
							</span>
						)}
					</div>
				</section>
				<aside className="rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-strip) p-5">
					<h2 className="text-sm font-semibold text-(--color-foreground)">边界确认</h2>
					<ul className="mt-3 space-y-3 text-xs leading-5 text-(--color-foreground-secondary)">
						<li>账户类型创建后不可转换。</li>
						<li>期初持仓可在创建后以“期初持仓”事件逐只录入。</li>
						<li>已提交事件不可覆盖，只能追加更正或冲正。</li>
						<li>备注和附件引用默认不出站到云模型。</li>
					</ul>
				</aside>
			</div>
		</div>
	);
}

function SnapshotSummary({ snapshot }: { readonly snapshot: ManualAccountLedger["snapshot"] }) {
	const metrics = [
		["总资产", formatMoney(snapshot.total_value)],
		["可用现金", formatMoney(snapshot.cash.available)],
		["已实现 PnL", formatMoney(snapshot.realized_pnl)],
		["未实现 PnL", formatMoney(snapshot.unrealized_pnl)],
		["累计费用", formatMoney(snapshot.total_fees)],
	] as const;
	return (
		<section aria-label="账户快照" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
			{metrics.map(([label, value]) => (
				<div
					key={label}
					className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-3 py-2.5"
				>
					<p className="text-[11px] text-(--color-foreground-tertiary)">{label}</p>
					<p className="mt-1 font-data text-base font-semibold tabular-nums text-(--color-foreground)">{value}</p>
				</div>
			))}
		</section>
	);
}

function PositionsTable({ snapshot }: { readonly snapshot: ManualAccountLedger["snapshot"] }) {
	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="flex items-center justify-between border-b border-(--color-border-subtle) px-4 py-3">
				<h2 className="text-sm font-semibold text-(--color-foreground)">持仓</h2>
				<span className="font-data text-xs text-(--color-foreground-tertiary)">{snapshot.positions.length} 只</span>
			</header>
			<div className="overflow-x-auto">
				<table className="w-full min-w-[680px] text-left text-xs">
					<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
						<tr>
							{["Instrument ID", "数量 / 可用", "成本 / 估值", "市值", "已实现 / 未实现", "费用"].map((label) => (
								<th key={label} className="px-3 py-2 font-medium">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{snapshot.positions.map((position) => (
							<tr
								key={position.instrument_id}
								className="border-t border-(--color-border-subtle) text-(--color-foreground)"
							>
								<td className="px-3 py-2 font-data font-semibold">{position.instrument_id}</td>
								<td className="px-3 py-2 font-data">
									{position.quantity} / {position.available_quantity}
								</td>
								<td className="px-3 py-2 font-data">
									{position.average_cost} / {position.last_price}
								</td>
								<td className="px-3 py-2 font-data">{formatMoney(position.market_value)}</td>
								<td className="px-3 py-2 font-data">
									{formatMoney(position.realized_pnl)} / {formatMoney(position.unrealized_pnl)}
								</td>
								<td className="px-3 py-2 font-data">{formatMoney(position.total_fees)}</td>
							</tr>
						))}
						{snapshot.positions.length === 0 && (
							<tr>
								<td colSpan={6} className="px-3 py-8 text-center text-(--color-foreground-tertiary)">
									暂无持仓；可录入期初持仓、买入或证券转入。
								</td>
							</tr>
						)}
					</tbody>
				</table>
			</div>
		</section>
	);
}

function LedgerPanel({
	events,
	snapshotEventCount,
	ledgerHash,
	valuationComplete,
	busy,
	reversalTarget,
	onReverse,
	onStartReversal,
	onCancelReversal,
	onStartCorrection,
}: {
	readonly events: readonly ManualAccountEvent[];
	readonly snapshotEventCount: number;
	readonly ledgerHash: string;
	readonly valuationComplete: boolean;
	readonly busy: boolean;
	readonly reversalTarget?: ManualAccountEvent | undefined;
	readonly onReverse: (target: ManualAccountEvent, reason: string) => Promise<void> | void;
	readonly onStartReversal: (event: ManualAccountEvent) => void;
	readonly onCancelReversal: () => void;
	readonly onStartCorrection: (event: ManualAccountEvent) => void;
}) {
	const [reason, setReason] = useState("");
	const controlledIds = useMemo(
		() =>
			new Set(
				events.flatMap((event) =>
					[event.reverses_event_id, event.corrects_event_id].filter((value): value is string => Boolean(value)),
				),
			),
		[events],
	);
	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<div className="flex items-center justify-between gap-3">
					<h2 className="text-sm font-semibold text-(--color-foreground)">流水与数据完整性</h2>
					<span
						className={`rounded-full px-2 py-0.5 text-[11px] ${events.length === snapshotEventCount && valuationComplete ? "bg-(--color-status-healthy-bg) text-(--color-status-healthy-fg)" : "bg-(--color-risk-warning-bg) text-(--color-risk-warning-fg)"}`}
					>
						{events.length === snapshotEventCount && valuationComplete ? "重建完整" : "需要核对"}
					</span>
				</div>
				<p className="mt-1 break-all font-data text-xs text-(--color-foreground-tertiary)">{ledgerHash}</p>
				<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">不可直接编辑；冲正和更正会追加新事件</p>
			</header>
			{reversalTarget && (
				<div className="border-b border-(--color-border-subtle) bg-(--color-risk-warning-bg) p-3">
					<p className="text-xs font-medium text-(--color-risk-warning-fg)">冲正 {reversalTarget.event_id}</p>
					<textarea
						aria-label="冲正原因"
						className={`${INPUT_CLASS} mt-2 min-h-16 w-full resize-y font-sans`}
						value={reason}
						onChange={(event) => setReason(event.currentTarget.value)}
					/>
					<div className="mt-2 flex justify-end gap-2">
						<Button
							type="button"
							variant="outline"
							size="sm"
							disabled={busy}
							onClick={() => {
								setReason("");
								onCancelReversal();
							}}
						>
							取消
						</Button>
						<Button
							type="button"
							size="sm"
							disabled={busy || !reason.trim()}
							onClick={() => void onReverse(reversalTarget, reason.trim())}
						>
							确认追加冲正
						</Button>
					</div>
				</div>
			)}
			<div className="max-h-[520px] overflow-y-auto">
				{events.map((event) => {
					const controllable =
						!["reversal", "correction"].includes(event.event_type) && !controlledIds.has(event.event_id);
					return (
						<article key={event.event_id} className="border-b border-(--color-border-subtle) px-4 py-3 last:border-b-0">
							<div className="flex items-start justify-between gap-3">
								<div>
									<div className="flex flex-wrap items-center gap-2">
										<span className="text-xs font-semibold text-(--color-foreground)">
											{EVENT_LABELS[event.event_type] ?? event.event_type}
										</span>
										<span className="font-data text-xs text-(--color-foreground-tertiary)">{event.event_id}</span>
									</div>
									<p className="mt-1 text-xs text-(--color-foreground-secondary)">{event.note || "无备注"}</p>
									<p className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">
										{event.trade_date} · 净现金 {event.net_cash} · 数量 {event.quantity} · 费用 {event.fees}
									</p>
									{event.attachment_refs.length > 0 && (
										<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
											附件：{event.attachment_refs.join("、")}
										</p>
									)}
								</div>
								{controllable && (
									<div className="flex shrink-0 gap-1">
										<Button
											type="button"
											variant="ghost"
											size="sm"
											aria-label={`更正 ${event.event_id}`}
											onClick={() => onStartCorrection(event)}
										>
											更正
										</Button>
										<Button
											type="button"
											variant="ghost"
											size="sm"
											aria-label={`冲正 ${event.event_id}`}
											onClick={() => {
												setReason("");
												onStartReversal(event);
											}}
										>
											冲正
										</Button>
									</div>
								)}
							</div>
							<p className="mt-2 break-all font-data text-[9px] text-(--color-foreground-tertiary)">
								{event.event_hash}
							</p>
						</article>
					);
				})}
				{events.length === 0 && (
					<p className="p-6 text-center text-xs text-(--color-foreground-tertiary)">尚无账户事件</p>
				)}
			</div>
		</section>
	);
}

export function ManualAccountWorkspace({
	accountId,
	asOf,
	onAccountSelected,
}: {
	readonly accountId?: string | undefined;
	readonly asOf?: string | undefined;
	readonly onAccountSelected?: ((accountId: string) => void) | undefined;
}) {
	const effectiveAsOf = asOf ?? localIsoDate();
	const queryClient = useQueryClient();
	const [message, setMessage] = useState<string | null>(null);
	const [correctionTarget, setCorrectionTarget] = useState<ManualAccountEvent>();
	const [reversalTarget, setReversalTarget] = useState<ManualAccountEvent>();
	const ledgerQuery = useQuery({
		queryKey: tradingKeys.manualLedger(accountId ?? "unselected", effectiveAsOf),
		queryFn: () => fetchManualAccountLedger(accountId ?? "", effectiveAsOf),
		enabled: Boolean(accountId),
	});
	const refresh = async () => {
		if (accountId)
			await queryClient.invalidateQueries({ queryKey: tradingKeys.manualLedger(accountId, effectiveAsOf) });
	};
	const recordMutation = useMutation({
		mutationFn: (body: ManualEventBody) => recordManualAccountEvent(accountId ?? "", body),
	});
	const correctionMutation = useMutation({
		mutationFn: ({ targetId, body }: { readonly targetId: string; readonly body: ManualEventBody }) =>
			correctManualAccountEvent(accountId ?? "", { corrects_event_id: targetId, replacement: body }),
	});
	const reversalMutation = useMutation({
		mutationFn: ({ target, reason }: { readonly target: ManualAccountEvent; readonly reason: string }) =>
			reverseManualAccountEvent(accountId ?? "", {
				actor: "local-user",
				idempotency_key: `manual-reversal:${crypto.randomUUID()}`,
				note: reason,
				reverses_event_id: target.event_id,
				settlement_date: effectiveAsOf,
				trade_date: effectiveAsOf,
			}),
	});
	const busy = recordMutation.isPending || correctionMutation.isPending || reversalMutation.isPending;

	if (!accountId) return <Onboarding asOf={effectiveAsOf} onAccountSelected={onAccountSelected} />;
	if (ledgerQuery.isLoading)
		return (
			<div className="p-6">
				<LoadingSkeleton variant="panel" rows={8} />
			</div>
		);
	if (ledgerQuery.isError || !ledgerQuery.data) {
		return (
			<div className="min-h-full bg-(--color-surface-canvas)">
				<AccountIdentityStrip kind="manual" accountId={accountId} />
				<div
					role="alert"
					className="m-6 flex items-center justify-between rounded-(--radius-md) border border-(--color-risk-critical-fg) p-4 text-sm"
				>
					<span>MANUAL 账本加载失败：{errorMessage(ledgerQuery.error)}</span>
					<Button type="button" variant="outline" onClick={() => void ledgerQuery.refetch()}>
						重试
					</Button>
				</div>
			</div>
		);
	}

	const { account, events, snapshot } = ledgerQuery.data;
	async function submitEvent(body: ManualEventBody): Promise<void> {
		try {
			if (correctionTarget) {
				await correctionMutation.mutateAsync({ targetId: correctionTarget.event_id, body });
				setCorrectionTarget(undefined);
				setMessage("更正事件已追加；原记录保持不变");
			} else {
				await recordMutation.mutateAsync(body);
				setMessage("事件已追加；原记录保持不变");
			}
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	async function reverse(target: ManualAccountEvent, reason: string): Promise<void> {
		try {
			await reversalMutation.mutateAsync({ target, reason });
			setReversalTarget(undefined);
			setMessage("冲正事件已追加；原记录仍可审计");
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	return (
		<div className="min-h-full bg-(--color-surface-canvas)">
			<AccountIdentityStrip kind="manual" accountId={account.account_id} accountName={account.name} />
			<div className="grid gap-4 p-4">
				<SnapshotSummary snapshot={snapshot} />
				{message && (
					<div
						role="status"
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs text-(--color-foreground-secondary)"
					>
						{message}
					</div>
				)}
				<div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.75fr)]">
					<div className="grid content-start gap-4">
						<ManualAccountEventComposer
							key={correctionTarget?.event_id ?? "new-event"}
							asOf={effectiveAsOf}
							busy={busy}
							correctionTarget={correctionTarget}
							onSubmit={submitEvent}
							onCancelCorrection={() => setCorrectionTarget(undefined)}
						/>
						<PositionsTable snapshot={snapshot} />
					</div>
					<LedgerPanel
						events={events}
						snapshotEventCount={snapshot.event_count}
						ledgerHash={snapshot.ledger_hash}
						valuationComplete={snapshot.valuation_complete}
						busy={busy}
						reversalTarget={reversalTarget}
						onReverse={reverse}
						onStartReversal={setReversalTarget}
						onCancelReversal={() => setReversalTarget(undefined)}
						onStartCorrection={(event) => {
							setReversalTarget(undefined);
							setCorrectionTarget(event);
						}}
					/>
				</div>
			</div>
		</div>
	);
}
