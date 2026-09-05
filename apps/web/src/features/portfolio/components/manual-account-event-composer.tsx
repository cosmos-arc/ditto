import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ManualAccountEvent, ManualBusinessEventType, ManualEventBody } from "../api/manual-accounts";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

const EVENT_OPTIONS: readonly { readonly value: ManualBusinessEventType; readonly label: string }[] = [
	{ value: "opening_cash", label: "期初现金" },
	{ value: "opening_position", label: "期初持仓" },
	{ value: "buy", label: "买入" },
	{ value: "sell", label: "卖出" },
	{ value: "deposit", label: "资金存入" },
	{ value: "withdrawal", label: "资金取出" },
	{ value: "fee", label: "费用" },
	{ value: "tax", label: "税费" },
	{ value: "interest", label: "利息" },
	{ value: "dividend", label: "分红" },
	{ value: "transfer_in", label: "证券转入" },
	{ value: "transfer_out", label: "证券转出" },
	{ value: "split", label: "拆分" },
	{ value: "merge", label: "合并" },
	{ value: "other_corporate_action", label: "其他公司行动" },
];

interface EventFormState {
	readonly eventType: ManualBusinessEventType;
	readonly tradeDate: string;
	readonly settlementDate: string;
	readonly instrumentId: string;
	readonly quantity: string;
	readonly price: string;
	readonly grossAmount: string;
	readonly fees: string;
	readonly tax: string;
	readonly note: string;
	readonly attachmentRefs: string;
	readonly externalReference: string;
}

function emptyForm(asOf: string, event?: ManualAccountEvent): EventFormState {
	const replacementType = event?.replacement_event_type ?? event?.event_type;
	const eventType = EVENT_OPTIONS.some((option) => option.value === replacementType)
		? (replacementType as ManualBusinessEventType)
		: "buy";
	return {
		eventType,
		tradeDate: event?.trade_date ?? asOf,
		settlementDate: event?.settlement_date ?? asOf,
		instrumentId: event?.instrument_id == null ? "" : String(event.instrument_id),
		quantity: event?.quantity ?? "",
		price: event?.price ?? "",
		grossAmount: event?.gross_amount ?? "",
		fees: event?.fees ?? "",
		tax: event?.tax ?? "",
		note: event?.note ?? "",
		attachmentRefs: event?.attachment_refs.join(", ") ?? "",
		externalReference: event?.external_reference ?? "",
	};
}

function numberValue(value: string): number {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: number): string {
	return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function preview(form: EventFormState): { readonly netCash: number; readonly positionDelta: string } {
	const quantity = numberValue(form.quantity);
	const explicitGross = numberValue(form.grossAmount);
	const gross = explicitGross > 0 ? explicitGross : quantity * numberValue(form.price);
	const costs = numberValue(form.fees) + numberValue(form.tax);
	let netCash = 0;
	if (["opening_cash", "deposit", "interest", "dividend", "sell"].includes(form.eventType)) {
		netCash = gross - costs;
	} else if (["withdrawal", "fee", "tax", "buy"].includes(form.eventType)) {
		netCash = -gross - costs;
	}
	if (Object.is(netCash, -0)) netCash = 0;
	let positionDelta = "0";
	if (quantity > 0 && ["opening_position", "buy", "transfer_in"].includes(form.eventType)) {
		positionDelta = `+${form.quantity}`;
	}
	if (quantity > 0 && ["sell", "transfer_out"].includes(form.eventType)) positionDelta = `-${form.quantity}`;
	if (["split", "merge", "other_corporate_action"].includes(form.eventType)) positionDelta = "按公司行动规则";
	return { netCash, positionDelta };
}

function idempotencyKey(prefix: string): string {
	return `${prefix}:${crypto.randomUUID()}`;
}

function toBody(form: EventFormState, prefix: string): ManualEventBody {
	return {
		actor: "local-user",
		attachment_refs: form.attachmentRefs
			.split(",")
			.map((value) => value.trim())
			.filter(Boolean),
		event_type: form.eventType,
		external_reference: form.externalReference.trim() || null,
		fees: form.fees || "0",
		gross_amount: form.grossAmount || "0",
		idempotency_key: idempotencyKey(prefix),
		instrument_id: form.instrumentId ? Number(form.instrumentId) : null,
		net_cash: null,
		note: form.note.trim(),
		price: form.price || "0",
		quantity: form.quantity || "0",
		settlement_date: form.settlementDate,
		tax: form.tax || "0",
		trade_date: form.tradeDate,
	};
}

function Field({
	label,
	value,
	type = "text",
	onChange,
}: {
	readonly label: string;
	readonly value: string;
	readonly type?: "text" | "date" | "number";
	readonly onChange: (value: string) => void;
}) {
	return (
		<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
			{label}
			<input
				aria-label={label}
				className={INPUT_CLASS}
				inputMode={type === "number" ? "decimal" : undefined}
				type={type === "number" ? "text" : type}
				value={value}
				onChange={(event) => onChange(event.currentTarget.value)}
			/>
		</label>
	);
}

export function ManualAccountEventComposer({
	asOf,
	busy,
	correctionTarget,
	onSubmit,
	onCancelCorrection,
}: {
	readonly asOf: string;
	readonly busy: boolean;
	readonly correctionTarget?: ManualAccountEvent | undefined;
	readonly onSubmit: (body: ManualEventBody) => Promise<void> | void;
	readonly onCancelCorrection?: () => void;
}) {
	const [form, setForm] = useState<EventFormState>(() => emptyForm(asOf, correctionTarget));
	const change = <K extends keyof EventFormState>(key: K, value: EventFormState[K]) =>
		setForm((current) => ({ ...current, [key]: value }));
	const estimate = useMemo(() => preview(form), [form]);
	const isCorrection = Boolean(correctionTarget);

	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<p className="text-sm font-semibold text-(--color-foreground)">
					{isCorrection ? `更正 ${correctionTarget?.event_id}` : "录入账户事件"}
				</p>
				<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
					提交前先核对净现金、费用和持仓变化；提交后只可追加冲正或更正。
				</p>
			</header>
			<div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					事件类型
					<select
						aria-label="事件类型"
						className={INPUT_CLASS}
						value={form.eventType}
						onChange={(event) => change("eventType", event.currentTarget.value as ManualBusinessEventType)}
					>
						{EVENT_OPTIONS.map((option) => (
							<option key={option.value} value={option.value}>
								{option.label}
							</option>
						))}
					</select>
				</label>
				<Field label="交易日期" type="date" value={form.tradeDate} onChange={(value) => change("tradeDate", value)} />
				<Field
					label="结算日期"
					type="date"
					value={form.settlementDate}
					onChange={(value) => change("settlementDate", value)}
				/>
				<Field
					label="Instrument ID"
					type="number"
					value={form.instrumentId}
					onChange={(value) => change("instrumentId", value)}
				/>
				<Field label="数量" type="number" value={form.quantity} onChange={(value) => change("quantity", value)} />
				<Field label="价格" type="number" value={form.price} onChange={(value) => change("price", value)} />
				<Field label="总额" type="number" value={form.grossAmount} onChange={(value) => change("grossAmount", value)} />
				<Field label="费用" type="number" value={form.fees} onChange={(value) => change("fees", value)} />
				<Field label="税费" type="number" value={form.tax} onChange={(value) => change("tax", value)} />
				<Field
					label="外部凭证号"
					value={form.externalReference}
					onChange={(value) => change("externalReference", value)}
				/>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary) sm:col-span-2">
					附件引用（逗号分隔）
					<input
						aria-label="附件引用（逗号分隔）"
						className={INPUT_CLASS}
						value={form.attachmentRefs}
						onChange={(event) => change("attachmentRefs", event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary) sm:col-span-2 xl:col-span-4">
					备注
					<textarea
						aria-label="备注"
						className={`${INPUT_CLASS} min-h-16 resize-y font-sans`}
						value={form.note}
						onChange={(event) => change("note", event.currentTarget.value)}
					/>
				</label>
			</div>
			<div className="flex flex-wrap items-center gap-4 border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-3">
				<div>
					<p className="text-[11px] text-(--color-foreground-tertiary)">预计净现金变化</p>
					<p className="font-data text-sm font-semibold text-(--color-foreground)">
						{estimate.netCash > 0 ? "+" : ""}
						{money(estimate.netCash)} CNY
					</p>
				</div>
				<div>
					<p className="text-[11px] text-(--color-foreground-tertiary)">预计持仓变化</p>
					<p className="font-data text-sm font-semibold text-(--color-foreground)">{estimate.positionDelta}</p>
				</div>
				<div className="ml-auto flex gap-2">
					{isCorrection && (
						<Button type="button" variant="outline" disabled={busy} onClick={onCancelCorrection}>
							取消更正
						</Button>
					)}
					<Button
						type="button"
						disabled={busy || !form.tradeDate || !form.settlementDate}
						onClick={() => void onSubmit(toBody(form, isCorrection ? "manual-correction" : "manual-event"))}
					>
						{busy ? "提交中…" : isCorrection ? "追加更正事件" : "记入不可变流水"}
					</Button>
				</div>
			</div>
			<p className="border-t border-(--color-border-subtle) px-4 py-2 text-[11px] text-(--color-foreground-tertiary)">
				备注和附件引用只进入本地账户账本，默认不提供给云模型。
			</p>
		</section>
	);
}
