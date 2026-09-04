import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import type { FillLedgerEntry } from "@/types";
import type { FillCorrectionKind } from "./fill-correction-form";

const DIRECTION_VARIANT = {
	BUY: "trade",
	SELL: "risk",
} as const;

const STATE_PRESENTATION = {
	effective: { label: "有效", variant: "healthy" },
	voided: { label: "已作废", variant: "idle" },
	replaced: { label: "已替换", variant: "warning" },
	unresolved: { label: "证据冲突", variant: "warning" },
} as const;

const CONSISTENCY_MESSAGE = {
	effective_with_adjustment: "后端同时返回有效成交与更正证据，状态未决，已禁止继续更正。",
	missing_effective_and_adjustment: "后端未返回有效成交或更正证据，状态未决，已禁止继续更正。",
	replacement_missing_raw: "替换事件指向的成交证据缺失，状态未决，已禁止继续更正。",
	replacement_not_resolved: "替换成交既未生效也没有后续更正，状态未决，已禁止继续更正。",
	replacement_cycle: "替换链形成循环，状态未决，已禁止继续更正。",
	orphan_adjustment: "更正事件缺少原始成交，关联证据状态未决，已禁止继续更正。",
	ghost_effective: "有效成交缺少原始流水，状态未决，已禁止继续更正。",
	replacement_identity_mismatch: "替换成交身份与原始成交不一致，状态未决，已禁止继续更正。",
} as const;

interface FillLedgerRowProps {
	readonly fill: FillLedgerEntry;
	readonly splitCount: number;
	readonly onCorrect: (kind: FillCorrectionKind, fill: FillLedgerEntry, trigger: HTMLButtonElement) => void;
}

function FillAdjustmentEvidence({ fill }: { readonly fill: FillLedgerEntry }) {
	if (!fill.adjustment) return null;
	return (
		<div className="col-span-2 mt-2 flex flex-col gap-1 border-t border-(--color-border-subtle) pt-2 text-xs text-(--color-foreground-tertiary) sm:col-span-5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3">
			<span className="max-w-full truncate font-data" title={fill.adjustment.id}>
				事件 {fill.adjustment.id}
			</span>
			<span className="text-(--color-foreground-secondary)">{fill.adjustment.reason}</span>
			{fill.adjustment.replacementFillId && (
				<span>
					替换为{" "}
					<span
						className="max-w-full truncate font-data text-(--color-foreground-secondary)"
						title={fill.adjustment.replacementFillId}
					>
						{fill.adjustment.replacementFillId}
					</span>
				</span>
			)}
			<time dateTime={fill.adjustment.createdAt}>{fill.adjustment.createdAt}</time>
		</div>
	);
}

function FillConsistencyWarning({ fill }: { readonly fill: FillLedgerEntry }) {
	if (!fill.consistencyIssue) return null;
	return (
		<p
			role="alert"
			className="col-span-2 mt-2 rounded-(--radius-sm) bg-(--color-risk-warning)/8 px-2 py-1.5 text-xs text-(--color-risk-warning-fg) sm:col-span-5"
		>
			{CONSISTENCY_MESSAGE[fill.consistencyIssue]}
		</p>
	);
}

export function FillLedgerRow({ fill, splitCount, onCorrect }: FillLedgerRowProps) {
	const state = STATE_PRESENTATION[fill.state];
	return (
		<li
			aria-label={`成交 ${fill.id}`}
			className="grid grid-cols-2 rounded-(--radius-sm) border border-transparent px-2 py-2 text-sm hover:border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg) sm:grid-cols-[minmax(8rem,1fr)_minmax(7rem,1fr)_5rem_5rem_minmax(7rem,auto)]"
		>
			<div className="col-span-2 grid grid-cols-2 items-center gap-x-3 gap-y-2 sm:col-span-5 sm:grid-cols-[minmax(8rem,1fr)_minmax(7rem,1fr)_5rem_5rem_minmax(7rem,auto)] sm:gap-2">
				<div className="col-span-2 min-w-0 sm:col-span-1">
					<div className="truncate font-data text-(--color-foreground)">{fill.id}</div>
					<div className="truncate text-xs text-(--color-foreground-tertiary)">
						{fill.intentId}
						{splitCount > 1 ? ` · 分批 ${splitCount} 笔` : ""}
					</div>
				</div>
				<div className="col-span-2 flex min-w-0 items-center gap-2 sm:col-span-1">
					<StatusBadge variant={DIRECTION_VARIANT[fill.direction]} label={fill.direction} size="sm" />
					<span className="truncate font-data text-(--color-foreground-secondary)">{fill.instrument}</span>
				</div>
				<div className="min-w-0">
					<span className="block text-xs text-(--color-foreground-muted) sm:hidden">数量</span>
					<span className="font-data tabular-nums text-(--color-foreground-tertiary)">
						{fill.quantity.toLocaleString()}
					</span>
				</div>
				<div className="min-w-0">
					<span className="block text-xs text-(--color-foreground-muted) sm:hidden">成交价</span>
					<span className="font-data tabular-nums text-(--color-foreground-tertiary)">
						¥{fill.fillPrice.toFixed(2)}
					</span>
				</div>
				<div className="col-span-2 flex min-w-0 items-center justify-between gap-2 sm:col-span-1 sm:justify-end">
					<span className="font-data text-xs tabular-nums text-(--color-foreground-tertiary)">
						<span className="sm:hidden">费用</span>
						<span className="hidden sm:inline">费</span> ¥{fill.fee.toFixed(2)}
					</span>
					<StatusBadge variant={state.variant} label={state.label} size="sm" />
				</div>
			</div>
			<FillAdjustmentEvidence fill={fill} />
			<FillConsistencyWarning fill={fill} />
			{fill.state === "effective" && (
				<div className="col-span-2 mt-2 flex flex-wrap justify-end gap-1 border-t border-(--color-border-subtle) pt-2 sm:col-span-5">
					<Button
						type="button"
						variant="ghost"
						size="xs"
						aria-label={`作废成交 ${fill.id}`}
						onClick={(event) => onCorrect("void", fill, event.currentTarget)}
					>
						作废
					</Button>
					<Button
						type="button"
						variant="outline"
						size="xs"
						aria-label={`替换成交 ${fill.id}`}
						onClick={(event) => onCorrect("replace", fill, event.currentTarget)}
					>
						替换
					</Button>
				</div>
			)}
		</li>
	);
}
