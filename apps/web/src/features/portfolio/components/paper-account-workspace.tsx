import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import {
	createPaperAccount,
	createPaperSession,
	fetchPaperAccountLedger,
	fetchPaperSession,
	operatePaperOrder,
	type PaperExecutionReceipt,
	type PaperSessionRead,
	pausePaperSession,
	reconcilePaperSession,
	recoverPaperSession,
} from "../api/paper-accounts";
import { tradingKeys } from "../api/query-keys";
import { AccountIdentityStrip } from "./account-identity-strip";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

function localIsoDate(): string {
	const now = new Date();
	const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
	return local.toISOString().slice(0, 10);
}

function nextCalendarDate(value: string): string {
	const date = new Date(`${value}T12:00:00Z`);
	date.setUTCDate(date.getUTCDate() + 1);
	return date.toISOString().slice(0, 10);
}

function requestKey(prefix: string): string {
	return `${prefix}:${crypto.randomUUID()}`;
}

function errorMessage(error: unknown): string {
	if (error instanceof ApiError) return error.detail ?? error.message;
	return error instanceof Error ? error.message : "Paper 操作失败";
}

function formatMoney(value: string | number): string {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return String(value);
	return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
}

function compactHash(value: string): string {
	return value.length > 30 ? `${value.slice(0, 18)}…${value.slice(-10)}` : value;
}

function PaperOnboarding({
	asOf,
	onWorkspaceSelected,
}: {
	readonly asOf: string;
	readonly onWorkspaceSelected?: ((accountId: string, sessionId: string) => void) | undefined;
}) {
	const [accountId, setAccountId] = useState("");
	const [accountName, setAccountName] = useState("");
	const [sessionId, setSessionId] = useState("");
	const [strategyId, setStrategyId] = useState("");
	const [initialCash, setInitialCash] = useState("");
	const [tradeDate, setTradeDate] = useState(asOf);
	const [message, setMessage] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	const ready = [accountId, accountName, sessionId, strategyId, initialCash, tradeDate].every((value) => value.trim());

	async function create(): Promise<void> {
		if (!ready) return;
		setBusy(true);
		setMessage(null);
		try {
			const normalizedAccount = accountId.trim();
			const normalizedSession = sessionId.trim();
			await createPaperAccount({
				account_id: normalizedAccount,
				currency: "CNY",
				idempotency_key: `${normalizedAccount}:create:v1`,
				initial_cash: initialCash,
				name: accountName.trim(),
				opened_at: `${tradeDate}T09:00:00+08:00`,
				trade_date: tradeDate,
			});
			await createPaperSession({
				account_id: normalizedAccount,
				idempotency_key: `${normalizedSession}:create:v1`,
				session_id: normalizedSession,
				start_immediately: true,
				strategy_id: strategyId.trim(),
				trade_date: tradeDate,
			});
			setMessage("PAPER 账户已隔离创建，会话已启动");
			onWorkspaceSelected?.(normalizedAccount, normalizedSession);
		} catch (error) {
			setMessage(errorMessage(error));
		} finally {
			setBusy(false);
		}
	}

	return (
		<div className="min-h-full bg-(--color-surface-canvas)">
			<AccountIdentityStrip kind="paper" />
			<div className="mx-auto grid max-w-6xl gap-5 p-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
				<section className="rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-5">
					<p className="font-data text-xs font-semibold tracking-[0.16em] text-(--color-risk-warning-fg)">
						PAPER SESSION
					</p>
					<h1 className="mt-2 text-xl font-semibold text-(--color-foreground)">创建隔离的模拟账户</h1>
					<p className="mt-2 max-w-2xl text-sm leading-6 text-(--color-foreground-secondary)">
						账户只接收 Ditto 模拟撮合产生的事实。订单、成交假设、行情快照和账本事件都保留独立哈希，不连接券商。
					</p>
					<div className="mt-5 grid gap-3 sm:grid-cols-2">
						{[
							["Paper 账户 ID", accountId, setAccountId],
							["Paper 账户名称", accountName, setAccountName],
							["Paper 会话 ID", sessionId, setSessionId],
							["策略 ID", strategyId, setStrategyId],
						].map(([label, value, setter]) => (
							<label key={label as string} className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
								{label as string}
								<input
									aria-label={label as string}
									className={INPUT_CLASS}
									value={value as string}
									onChange={(event) => (setter as (next: string) => void)(event.currentTarget.value)}
								/>
							</label>
						))}
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							交易日
							<input
								aria-label="交易日"
								type="date"
								className={INPUT_CLASS}
								value={tradeDate}
								onChange={(event) => setTradeDate(event.currentTarget.value)}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							期初现金
							<input
								aria-label="期初现金"
								inputMode="decimal"
								className={INPUT_CLASS}
								value={initialCash}
								onChange={(event) => setInitialCash(event.currentTarget.value)}
							/>
						</label>
					</div>
					<div className="mt-5 flex flex-wrap items-center gap-3">
						<Button type="button" disabled={busy || !ready} onClick={() => void create()}>
							{busy ? "创建并启动中…" : "创建 PAPER 账户并启动会话"}
						</Button>
						{message && (
							<span role="status" className="text-xs text-(--color-foreground-secondary)">
								{message}
							</span>
						)}
					</div>
				</section>
				<aside className="rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-strip) p-5">
					<h2 className="text-sm font-semibold text-(--color-foreground)">运行边界</h2>
					<ol className="mt-3 space-y-3 text-xs leading-5 text-(--color-foreground-secondary)">
						<li>1. 每个会话固定一个账户、策略和交易日。</li>
						<li>2. 行情可见性、手数、T+1、涨跌停和停牌规则 fail closed。</li>
						<li>3. 执行先持久化，再写账本；中断后由恢复入口补齐。</li>
						<li>4. 日终必须核对成交与账本数量和哈希。</li>
					</ol>
				</aside>
			</div>
		</div>
	);
}

function Metric({
	label,
	value,
	detail,
}: {
	readonly label: string;
	readonly value: string;
	readonly detail?: string;
}) {
	return (
		<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-3 py-2.5">
			<p className="text-[11px] text-(--color-foreground-tertiary)">{label}</p>
			<p className="mt-1 font-data text-base font-semibold tabular-nums text-(--color-foreground)">{value}</p>
			{detail && <p className="mt-1 text-xs text-(--color-foreground-tertiary)">{detail}</p>}
		</div>
	);
}

function SessionHealth({ data }: { readonly data: PaperSessionRead }) {
	const reconciliation = data.latest_reconciliation;
	const filled = data.executions.filter((execution) => execution.fill).length;
	return (
		<section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
			<Metric label="会话状态" value={data.session.status.toUpperCase()} detail={`revision ${data.session.revision}`} />
			<Metric label="订单 / 成交" value={`${data.executions.length} / ${filled}`} detail={data.session.trade_date} />
			<Metric
				label="日终对账"
				value={reconciliation ? (reconciliation.balanced ? "日终已平衡" : "日终不平衡") : "尚未执行"}
				detail={reconciliation?.checksum ? compactHash(reconciliation.checksum) : "需要显式运行"}
			/>
			<Metric label="策略" value={data.session.strategy_id} detail={data.session.session_id} />
		</section>
	);
}

function OrderComposer({
	tradeDate,
	busy,
	onSubmit,
}: {
	readonly tradeDate: string;
	readonly busy: boolean;
	readonly onSubmit: (body: Parameters<typeof operatePaperOrder>[1]) => Promise<void>;
}) {
	const [assetClass, setAssetClass] = useState<"stock" | "etf">("stock");
	const [instrumentId, setInstrumentId] = useState("600519");
	const [exchange, setExchange] = useState<"XSHG" | "XSHE">("XSHG");
	const [side, setSide] = useState<"buy" | "sell">("buy");
	const [orderType, setOrderType] = useState<"market" | "limit">("market");
	const [quantity, setQuantity] = useState("100");
	const [limitPrice, setLimitPrice] = useState("");
	const [close, setClose] = useState("10.00");
	const [prevClose, setPrevClose] = useState("9.90");
	const [positionQuantity, setPositionQuantity] = useState("0");
	const [availableQuantity, setAvailableQuantity] = useState("0");
	const [settlementDate, setSettlementDate] = useState(() => nextCalendarDate(tradeDate));
	const [sourceSnapshotId, setSourceSnapshotId] = useState(`paper-ui:${tradeDate}:600519`);

	async function submit(): Promise<void> {
		const instrument = Number(instrumentId);
		const price = Number(close);
		const previous = Number(prevClose);
		const decisionAt = `${tradeDate}T15:00:00+08:00`;
		await onSubmit({
			assumption: { assumption_id: "paper-default-v1", reference_price_field: "close", slippage_bps: 1, version: 1 },
			available_quantity: Number(availableQuantity),
			decision_at: decisionAt,
			execution_at: decisionAt,
			idempotency_key: requestKey("paper-operate"),
			instrument_id: instrument,
			market: {
				amount: price * 1_000_000,
				avg_volume_20d: 1_000_000,
				close: price,
				dataset_id: assetClass === "stock" ? "stock_daily" : "etf_daily",
				high: price,
				is_suspended: false,
				limit_down: Number((previous * 0.9).toFixed(2)),
				limit_up: Number((previous * 1.1).toFixed(2)),
				low: price,
				observed_at: decisionAt,
				open: price,
				prev_close: previous,
				publication_cutoff: decisionAt,
				source: "operator-snapshot",
				source_snapshot_id: sourceSnapshotId,
				volume: 1_000_000,
			},
			order_id: requestKey("paper-order"),
			order_type: orderType,
			position_quantity: Number(positionQuantity),
			price: orderType === "limit" ? Number(limitPrice) : null,
			quantity: Number(quantity),
			rules: {
				asset_class: assetClass,
				board_segment: assetClass === "stock" ? "main" : "fund",
				commission_rate: 0.0003,
				currency: "CNY",
				exchange,
				lifecycle_state: "listed",
				lot_size: 100,
				min_commission: 5,
				multiplier: 1,
				price_limit_pct: 0.1,
				settlement_cycle: 1,
				stamp_duty_rate: assetClass === "stock" ? 0.0005 : 0,
				tick_size: 0.01,
				transfer_fee_rate: 0.00001,
			},
			settlement_date: settlementDate,
			side,
			trade_date: tradeDate,
		});
	}

	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<h2 className="text-sm font-semibold text-(--color-foreground)">模拟订单</h2>
				<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
					提交完整市场快照与规则；撮合结果可能成交、推迟或拒绝。
				</p>
			</header>
			<div className="grid gap-3 p-4 sm:grid-cols-2">
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					资产类型
					<select
						aria-label="Paper 资产类型"
						className={INPUT_CLASS}
						value={assetClass}
						onChange={(event) => {
							const next = event.currentTarget.value as "stock" | "etf";
							setAssetClass(next);
							if (next === "etf" && instrumentId === "600519") {
								setInstrumentId("510300");
								setSourceSnapshotId(`paper-ui:${tradeDate}:510300`);
							}
						}}
					>
						<option value="stock">A 股个股</option>
						<option value="etf">ETF</option>
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Instrument ID
					<input
						aria-label="Paper Instrument ID"
						className={INPUT_CLASS}
						value={instrumentId}
						onChange={(event) => setInstrumentId(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					交易所
					<select
						aria-label="Paper 交易所"
						className={INPUT_CLASS}
						value={exchange}
						onChange={(event) => setExchange(event.currentTarget.value as "XSHG" | "XSHE")}
					>
						<option value="XSHG">上海 XSHG</option>
						<option value="XSHE">深圳 XSHE</option>
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					方向
					<select
						aria-label="Paper 方向"
						className={INPUT_CLASS}
						value={side}
						onChange={(event) => setSide(event.currentTarget.value as "buy" | "sell")}
					>
						<option value="buy">买入</option>
						<option value="sell">卖出</option>
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					订单类型
					<select
						aria-label="Paper 订单类型"
						className={INPUT_CLASS}
						value={orderType}
						onChange={(event) => setOrderType(event.currentTarget.value as "market" | "limit")}
					>
						<option value="market">市价</option>
						<option value="limit">限价</option>
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					数量
					<input
						aria-label="Paper 数量"
						className={INPUT_CLASS}
						value={quantity}
						onChange={(event) => setQuantity(event.currentTarget.value)}
					/>
				</label>
				{orderType === "limit" && (
					<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
						限价
						<input
							aria-label="Paper 限价"
							className={INPUT_CLASS}
							value={limitPrice}
							onChange={(event) => setLimitPrice(event.currentTarget.value)}
						/>
					</label>
				)}
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					收盘 / 参考价
					<input
						aria-label="Paper 收盘价"
						className={INPUT_CLASS}
						value={close}
						onChange={(event) => setClose(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					昨收
					<input
						aria-label="Paper 昨收"
						className={INPUT_CLASS}
						value={prevClose}
						onChange={(event) => setPrevClose(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					持仓 / T+1 可用
					<div className="grid grid-cols-2 gap-2">
						<input
							aria-label="Paper 持仓数量"
							className={INPUT_CLASS}
							value={positionQuantity}
							onChange={(event) => setPositionQuantity(event.currentTarget.value)}
						/>
						<input
							aria-label="Paper 可用数量"
							className={INPUT_CLASS}
							value={availableQuantity}
							onChange={(event) => setAvailableQuantity(event.currentTarget.value)}
						/>
					</div>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					交收日
					<input
						aria-label="Paper 交收日"
						type="date"
						className={INPUT_CLASS}
						value={settlementDate}
						onChange={(event) => setSettlementDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary) sm:col-span-2">
					行情快照 ID
					<input
						aria-label="Paper 行情快照 ID"
						className={INPUT_CLASS}
						value={sourceSnapshotId}
						onChange={(event) => setSourceSnapshotId(event.currentTarget.value)}
					/>
				</label>
			</div>
			<footer className="flex items-center justify-between border-t border-(--color-border-subtle) px-4 py-3">
				<span className="text-xs text-(--color-foreground-tertiary)">
					{assetClass === "stock" ? "A 股个股 · 卖出收印花税" : "ETF · 免印花税"} · 100 股一手 · T+1 · 默认 1 bps 滑点
				</span>
				<Button
					type="button"
					disabled={busy || !instrumentId || !quantity || !close || !prevClose}
					onClick={() => void submit()}
				>
					提交模拟订单
				</Button>
			</footer>
		</section>
	);
}

function ExecutionList({
	executions,
	selectedId,
	onSelect,
}: {
	readonly executions: readonly PaperExecutionReceipt[];
	readonly selectedId?: string | undefined;
	readonly onSelect: (id: string) => void;
}) {
	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="flex items-center justify-between border-b border-(--color-border-subtle) px-4 py-3">
				<h2 className="text-sm font-semibold text-(--color-foreground)">订单与成交</h2>
				<span className="font-data text-xs text-(--color-foreground-tertiary)">{executions.length}</span>
			</header>
			<div className="divide-y divide-(--color-border-subtle)">
				{executions.map((execution) => (
					<button
						type="button"
						key={execution.execution_id}
						onClick={() => onSelect(execution.execution_id)}
						className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 text-left hover:bg-(--color-interaction-hover-subtle-bg) ${selectedId === execution.execution_id ? "bg-(--color-surface-strip)" : ""}`}
					>
						<div className="min-w-0">
							<p className="truncate font-data text-xs font-semibold text-(--color-foreground)">{execution.order_id}</p>
							<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">
								{execution.fill
									? `${execution.fill.direction.toUpperCase()} ${execution.fill.quantity} @ ${execution.fill.fill_price}`
									: (execution.reason ?? "无成交")}
							</p>
						</div>
						<span
							className={`self-start rounded-full border px-2 py-0.5 font-data text-xs ${execution.fill ? "border-(--color-status-healthy-fg) text-(--color-status-healthy-fg)" : "border-(--color-risk-warning-fg) text-(--color-risk-warning-fg)"}`}
						>
							{execution.reality_status}
						</span>
					</button>
				))}
				{executions.length === 0 && (
					<p className="p-6 text-center text-xs text-(--color-foreground-tertiary)">尚无模拟订单</p>
				)}
			</div>
		</section>
	);
}

function FillInspector({ execution }: { readonly execution?: PaperExecutionReceipt | undefined }) {
	if (!execution)
		return (
			<section className="rounded-(--radius-md) border border-(--color-border-subtle) p-5 text-xs text-(--color-foreground-tertiary)">
				选择一笔执行查看证据
			</section>
		);
	const fill = execution.fill;
	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<h2 className="text-sm font-semibold text-(--color-foreground)">成交假设与快照血缘</h2>
				<p className="mt-1 break-all font-data text-xs text-(--color-foreground-tertiary)">{execution.request_hash}</p>
			</header>
			{fill ? (
				<div className="grid gap-4 p-4">
					<div className="grid grid-cols-2 gap-2 text-xs">
						<Metric label="参考 / 成交" value={`${fill.reference_price} / ${fill.fill_price}`} />
						<Metric label="滑点" value={formatMoney(fill.slippage)} detail="成交价差总额" />
						<Metric
							label="佣金 / 过户费"
							value={`${formatMoney(fill.commission)} / ${formatMoney(fill.transfer_fee)}`}
						/>
						<Metric label="税费 / 总成本" value={`${formatMoney(fill.tax)} / ${formatMoney(fill.total_cost)}`} />
					</div>
					<dl className="grid gap-2 text-xs">
						{[
							["assumption", fill.assumption_hash],
							["market snapshot", fill.market_snapshot_hash],
							["market lineage", fill.market_lineage_hash],
							["ledger event", execution.ledger_event_id ?? "未入账"],
						].map(([label, value]) => (
							<div key={label} className="grid gap-1 rounded-(--radius-sm) bg-(--color-surface-strip) px-3 py-2">
								<dt className="uppercase tracking-wide text-(--color-foreground-tertiary)">{label}</dt>
								<dd className="break-all font-data text-(--color-foreground-secondary)">{value}</dd>
							</div>
						))}
					</dl>
				</div>
			) : (
				<div className="p-4">
					<p className="text-sm font-medium text-(--color-risk-warning-fg)">未生成成交</p>
					<p className="mt-2 font-data text-xs text-(--color-foreground-secondary)">
						{execution.reason ?? "撮合未成交"}
					</p>
					<p className="mt-3 text-xs text-(--color-foreground-tertiary)">
						失败或推迟会保留执行记录，但不会伪造 Fill 或账本事件。
					</p>
				</div>
			)}
		</section>
	);
}

function DriftAttribution({ executions }: { readonly executions: readonly PaperExecutionReceipt[] }) {
	const figures = useMemo(() => {
		const fills = executions.flatMap((execution) => (execution.fill ? [execution.fill] : []));
		return {
			notFilled: executions.length - fills.length,
			slippage: fills.reduce((sum, fill) => sum + fill.slippage, 0),
			cost: fills.reduce((sum, fill) => sum + fill.total_cost, 0),
			tax: fills.reduce((sum, fill) => sum + fill.tax, 0),
		};
	}, [executions]);
	return (
		<section
			data-slot="paper-drift"
			className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4"
		>
			<h2 className="text-sm font-semibold text-(--color-foreground)">执行偏差归因</h2>
			<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
				先解释 Model 意图进入 Paper 后的执行损耗；正式持仓权重 drift 由统一比较视图提供。
			</p>
			<div className="mt-4 grid grid-cols-2 gap-2">
				<Metric label="未成交" value={`${figures.notFilled} 笔未成交 / 推迟`} />
				<Metric label="总滑点" value={formatMoney(figures.slippage)} />
				<Metric label="费用" value={formatMoney(figures.cost - figures.tax)} />
				<Metric label="税费" value={formatMoney(figures.tax)} />
			</div>
			<p className="mt-3 rounded-(--radius-sm) bg-(--color-surface-strip) px-3 py-2 text-[11px] text-(--color-foreground-secondary)">
				Model → Paper 权重差：等待 PortfolioComparisonView；当前不从 UI 推断。
			</p>
		</section>
	);
}

export function PaperAccountWorkspace({
	accountId,
	sessionId,
	asOf,
	onWorkspaceSelected,
}: {
	readonly accountId?: string | undefined;
	readonly sessionId?: string | undefined;
	readonly asOf?: string | undefined;
	readonly onWorkspaceSelected?: ((accountId: string, sessionId: string) => void) | undefined;
}) {
	const effectiveAsOf = asOf ?? localIsoDate();
	const queryClient = useQueryClient();
	const [selectedExecutionId, setSelectedExecutionId] = useState<string>();
	const [message, setMessage] = useState<string | null>(null);
	const sessionQuery = useQuery({
		queryKey: tradingKeys.paperSession(sessionId ?? "unselected"),
		queryFn: () => fetchPaperSession(sessionId ?? ""),
		enabled: Boolean(sessionId),
	});
	const ledgerQuery = useQuery({
		queryKey: tradingKeys.paperLedger(accountId ?? "unselected", effectiveAsOf),
		queryFn: () => fetchPaperAccountLedger(accountId ?? "", effectiveAsOf),
		enabled: Boolean(accountId),
	});
	const operateMutation = useMutation({
		mutationFn: (body: Parameters<typeof operatePaperOrder>[1]) => operatePaperOrder(sessionId ?? "", body),
	});
	const pauseMutation = useMutation({
		mutationFn: () =>
			pausePaperSession(sessionId ?? "", {
				idempotency_key: requestKey("paper-pause"),
				reason: "operator pause from Paper workspace",
			}),
	});
	const reconcileMutation = useMutation({
		mutationFn: () => reconcilePaperSession(sessionId ?? "", { idempotency_key: requestKey("paper-eod") }),
	});
	const recoverMutation = useMutation({
		mutationFn: () => recoverPaperSession(sessionId ?? "", { idempotency_key: requestKey("paper-recover") }),
	});
	const busy =
		operateMutation.isPending || pauseMutation.isPending || reconcileMutation.isPending || recoverMutation.isPending;

	if (!accountId || !sessionId)
		return <PaperOnboarding asOf={effectiveAsOf} onWorkspaceSelected={onWorkspaceSelected} />;
	const selectedAccountId = accountId;
	const selectedSessionId = sessionId;

	async function refresh(): Promise<void> {
		await Promise.all([
			queryClient.invalidateQueries({ queryKey: tradingKeys.paperSession(selectedSessionId) }),
			queryClient.invalidateQueries({ queryKey: tradingKeys.paperLedger(selectedAccountId, effectiveAsOf) }),
		]);
	}

	async function operate(body: Parameters<typeof operatePaperOrder>[1]): Promise<void> {
		try {
			const receipt = await operateMutation.mutateAsync(body);
			setSelectedExecutionId(receipt.execution_id);
			setMessage(
				receipt.fill
					? `模拟成交已持久化：${receipt.fill.quantity} @ ${receipt.fill.fill_price}`
					: `订单未成交：${receipt.reason ?? receipt.reality_status}`,
			);
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	async function pause(): Promise<void> {
		try {
			await pauseMutation.mutateAsync();
			setMessage("会话已暂停；新订单将 fail closed，恢复账本缺口仍可执行");
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	async function reconcile(): Promise<void> {
		try {
			const receipt = await reconcileMutation.mutateAsync();
			setMessage(
				receipt.balanced
					? `日终对账通过：${receipt.ledger_fill_count}/${receipt.fill_count} 笔成交已入账`
					: `日终对账失败：${receipt.ledger_fill_count}/${receipt.fill_count}，需要先恢复`,
			);
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	async function recover(): Promise<void> {
		try {
			const receipt = await recoverMutation.mutateAsync();
			setMessage(`恢复检查完成：${receipt.recovered_execution_count} 条执行记录已核验`);
			await refresh();
		} catch (error) {
			setMessage(errorMessage(error));
		}
	}

	if (sessionQuery.isLoading || ledgerQuery.isLoading)
		return (
			<div className="p-6">
				<LoadingSkeleton variant="panel" rows={9} />
			</div>
		);
	if (sessionQuery.isError || ledgerQuery.isError || !sessionQuery.data || !ledgerQuery.data) {
		return (
			<div className="min-h-full bg-(--color-surface-canvas)">
				<AccountIdentityStrip kind="paper" accountId={accountId} />
				<div
					role="alert"
					className="m-6 rounded-(--radius-md) border border-(--color-risk-critical-fg) p-4 text-sm text-(--color-foreground)"
				>
					<p>PAPER 会话加载失败，未使用原型或旧账本替代。</p>
					<p className="mt-1 text-xs text-(--color-foreground-secondary)">
						{errorMessage(sessionQuery.error ?? ledgerQuery.error)}
					</p>
					<Button
						className="mt-3"
						type="button"
						variant="outline"
						onClick={() => void Promise.all([sessionQuery.refetch(), ledgerQuery.refetch()])}
					>
						重试
					</Button>
				</div>
			</div>
		);
	}

	const session = sessionQuery.data;
	const ledger = ledgerQuery.data;
	const selectedExecution =
		session.executions.find((item) => item.execution_id === selectedExecutionId) ?? session.executions[0];

	return (
		<div className="min-h-full bg-(--color-surface-canvas)">
			<AccountIdentityStrip kind="paper" accountId={ledger.account.account_id} accountName={ledger.account.name} />
			<div className="grid gap-4 p-4">
				<SessionHealth data={session} />
				<section className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2">
					<div>
						<h2 className="text-xs font-semibold text-(--color-foreground)">会话控制</h2>
						<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
							暂停阻止新撮合；恢复只补齐已持久化执行的账本链接。
						</p>
					</div>
					<div className="flex flex-wrap gap-2">
						<Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void reconcile()}>
							日终对账
						</Button>
						<Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void recover()}>
							恢复账本缺口
						</Button>
						<Button
							type="button"
							size="sm"
							variant="outline"
							disabled={busy || session.session.status !== "running"}
							onClick={() => void pause()}
						>
							暂停会话
						</Button>
					</div>
				</section>
				{message && (
					<div
						role="status"
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-3 py-2 text-xs text-(--color-foreground-secondary)"
					>
						{message}
					</div>
				)}
				<div className="grid gap-4 xl:grid-cols-[minmax(360px,0.86fr)_minmax(0,1.14fr)]">
					<div className="grid content-start gap-4">
						<OrderComposer
							tradeDate={session.session.trade_date}
							busy={busy || session.session.status !== "running"}
							onSubmit={operate}
						/>
						<ExecutionList
							executions={session.executions}
							selectedId={selectedExecution?.execution_id}
							onSelect={setSelectedExecutionId}
						/>
					</div>
					<div className="grid content-start gap-4">
						<FillInspector execution={selectedExecution} />
						<DriftAttribution executions={session.executions} />
						<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4">
							<div className="grid gap-2 sm:grid-cols-3">
								<Metric label="总资产" value={formatMoney(ledger.snapshot.total_value)} />
								<Metric label="可用现金" value={formatMoney(ledger.snapshot.cash.available)} />
								<Metric label="累计成本" value={formatMoney(ledger.snapshot.total_fees)} />
							</div>
							<p className="mt-3 break-all font-data text-[9px] text-(--color-foreground-tertiary)">
								{ledger.snapshot.ledger_hash}
							</p>
						</section>
					</div>
				</div>
			</div>
		</div>
	);
}
