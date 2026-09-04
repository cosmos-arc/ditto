import type { FillLedgerEntry } from "@/types";
import type { CorrectFillCommand } from "../hooks/use-correct-fill";

export type FillCorrectionKind = "void" | "replace";

export type FillCorrectionFormState = {
	readonly tradeDate: string;
	readonly quantity: string;
	readonly fillPrice: string;
	readonly fee: string;
	readonly slippage: string;
	readonly notes: string;
	readonly reason: string;
};

export type FillCorrectionIds = {
	readonly adjustmentId: string;
	readonly replacementFillId: string;
};

type BuildCorrectionResult = { readonly command: CorrectFillCommand } | { readonly error: string };

let fallbackSequence = 0;

function uniqueSuffix(): string {
	if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
	fallbackSequence += 1;
	return `${Date.now()}-${fallbackSequence}`;
}

export function createFillCorrectionIds(fillId: string, kind: FillCorrectionKind): FillCorrectionIds {
	const suffix = uniqueSuffix();
	return {
		adjustmentId: `adjustment-${kind}-${fillId}-${suffix}`,
		replacementFillId: `fill-${fillId}-replacement-${suffix}`,
	};
}

export function createFillCorrectionForm(fill: FillLedgerEntry): FillCorrectionFormState {
	return {
		tradeDate: fill.tradeDate,
		quantity: String(fill.quantity),
		fillPrice: String(fill.fillPrice),
		fee: String(fill.fee),
		slippage: String(fill.slippage),
		notes: fill.notes,
		reason: "",
	};
}

function finiteNumber(value: string): number | null {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

function validateReplacement(form: FillCorrectionFormState): string | null {
	const quantity = finiteNumber(form.quantity);
	const fillPrice = finiteNumber(form.fillPrice);
	const fee = finiteNumber(form.fee);
	const slippage = finiteNumber(form.slippage);
	if (!form.tradeDate) return "请填写替换成交日期";
	if (quantity === null || !Number.isInteger(quantity) || quantity <= 0) return "替换成交数量必须为正整数";
	if (fillPrice === null || fillPrice <= 0) return "替换成交价格必须大于 0";
	if (fee === null || fee < 0) return "手续费不能小于 0";
	if (slippage === null) return "滑点必须为有效数字";
	return null;
}

export function buildFillCorrectionCommand(params: {
	readonly fill: FillLedgerEntry;
	readonly kind: FillCorrectionKind;
	readonly form: FillCorrectionFormState;
	readonly ids: FillCorrectionIds;
}): BuildCorrectionResult {
	const { fill, kind, form, ids } = params;
	const reason = form.reason.trim();
	if (!reason) return { error: "请填写更正原因" };
	if (kind === "void") {
		return { command: { kind, fillId: fill.id, payload: { adjustment_id: ids.adjustmentId, reason } } };
	}
	const error = validateReplacement(form);
	if (error) return { error };
	return {
		command: {
			kind,
			fillId: fill.id,
			payload: {
				adjustment_id: ids.adjustmentId,
				replacement_fill_id: ids.replacementFillId,
				trade_date: form.tradeDate,
				quantity: Number(form.quantity),
				fill_price: Number(form.fillPrice),
				reason,
				fee: Number(form.fee),
				slippage: Number(form.slippage),
				notes: form.notes,
			},
		},
	};
}
