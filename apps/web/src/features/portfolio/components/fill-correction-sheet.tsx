import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ApiError } from "@/lib/api-client";
import type { FillLedgerEntry } from "@/types";
import { classifyMutationFailure } from "../api/mutation-result";
import { useCorrectFill } from "../hooks";
import type { CorrectFillCommand } from "../hooks/use-correct-fill";
import { FillCorrectionFields } from "./fill-correction-fields";
import {
	buildFillCorrectionCommand,
	createFillCorrectionForm,
	createFillCorrectionIds,
	type FillCorrectionFormState,
	type FillCorrectionKind,
} from "./fill-correction-form";

interface FillCorrectionSheetProps {
	readonly fill: FillLedgerEntry;
	readonly kind: FillCorrectionKind;
	readonly open: boolean;
	readonly triggerElement: HTMLButtonElement | null;
	readonly onOpenChange: (open: boolean) => void;
	readonly onClosed: () => void;
	readonly onSuccess: (message: string) => void;
	readonly onRefresh: () => void;
}

function OriginalFillEvidence({ fill }: { readonly fill: FillLedgerEntry }) {
	return (
		<section
			aria-label="不可变原始成交证据"
			className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-2) p-3"
		>
			<div className="mb-2 flex min-w-0 items-start justify-between gap-2">
				<h3 className="text-(length:--text-sm) font-medium text-(--color-foreground)">原始证据 · 只读</h3>
				<span className="min-w-0 break-all text-right font-data text-xs text-(--color-foreground-secondary)">
					{fill.id}
				</span>
			</div>
			<dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs sm:grid-cols-3">
				<div className="min-w-0">
					<dt className="text-(--color-foreground-secondary)">意图</dt>
					<dd className="min-w-0 break-all font-data text-(--color-foreground-secondary)">{fill.intentId}</dd>
				</div>
				<div>
					<dt className="text-(--color-foreground-secondary)">成交日</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{fill.tradeDate}</dd>
				</div>
				<div>
					<dt className="text-(--color-foreground-secondary)">标的 / 方向</dt>
					<dd className="font-data text-(--color-foreground-secondary)">
						{fill.instrument} · {fill.direction}
					</dd>
				</div>
				<div>
					<dt className="text-(--color-foreground-secondary)">数量</dt>
					<dd className="font-data text-(--color-foreground-secondary)">{fill.quantity.toLocaleString()}</dd>
				</div>
				<div>
					<dt className="text-(--color-foreground-secondary)">成交价</dt>
					<dd className="font-data text-(--color-foreground-secondary)">¥{fill.fillPrice.toFixed(2)}</dd>
				</div>
				<div>
					<dt className="text-(--color-foreground-secondary)">费用 / 滑点</dt>
					<dd className="font-data text-(--color-foreground-secondary)">
						¥{fill.fee.toFixed(2)} / {fill.slippage}
					</dd>
				</div>
			</dl>
			{fill.notes && <p className="mt-2 break-words text-xs text-(--color-foreground-secondary)">{fill.notes}</p>}
		</section>
	);
}

function describeCorrectionError(error: unknown): string | null {
	if (!error) return null;
	const failureKind = classifyMutationFailure(error);
	if (failureKind === "unknown") return "提交结果未知；重试将复用同一更正标识，避免重复追加。";
	if (failureKind === "conflict" && error instanceof ApiError) return `更正冲突：${error.message}`;
	if (error instanceof ApiError) return `成交更正失败：${error.message}`;
	return null;
}

export function FillCorrectionSheet(props: FillCorrectionSheetProps) {
	const { fill, kind, open, triggerElement, onOpenChange, onClosed, onSuccess, onRefresh } = props;
	const mutation = useCorrectFill();
	const [form, setForm] = useState(() => createFillCorrectionForm(fill));
	const [ids] = useState(() => createFillCorrectionIds(fill.id, kind));
	const [validationError, setValidationError] = useState<string | null>(null);
	const [lastCommand, setLastCommand] = useState<CorrectFillCommand | null>(null);
	const title = kind === "void" ? "作废成交" : "替换成交";
	const action = kind === "void" ? "作废" : "替换";
	const errorMessage = validationError ?? describeCorrectionError(mutation.error);
	const failureKind = classifyMutationFailure(mutation.error);
	const isConflict = failureKind === "conflict";
	const canRetry = mutation.isError && failureKind === "unknown" && lastCommand !== null;
	const mustPreserveCommand = mutation.isPending || canRetry;
	const isLocked = mustPreserveCommand;

	function updateForm(field: keyof FillCorrectionFormState, value: string) {
		setForm((current) => ({ ...current, [field]: value }));
	}

	function execute(command: CorrectFillCommand) {
		mutation.mutate(command, {
			onSuccess: () => {
				onSuccess(`${fill.id} 已追加${action}`);
				onOpenChange(false);
			},
		});
	}

	function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setValidationError(null);
		const result = buildFillCorrectionCommand({ fill, kind, form, ids });
		if ("error" in result) {
			setValidationError(result.error);
			return;
		}
		setLastCommand(result.command);
		execute(result.command);
	}

	function closeAndRefresh() {
		onOpenChange(false);
		onRefresh();
	}

	function handleOpenChange(nextOpen: boolean) {
		if (!nextOpen && mustPreserveCommand) return;
		onOpenChange(nextOpen);
	}

	return (
		<Sheet open={open} onOpenChange={handleOpenChange}>
			<SheetContent
				side="right"
				onCloseAutoFocus={(event) => {
					event.preventDefault();
					triggerElement?.focus();
					onClosed();
				}}
				className="w-full overflow-y-auto sm:max-w-(--width-drawer)"
			>
				<form className="flex min-h-full flex-col gap-4 p-4" onSubmit={submit}>
					<SheetHeader>
						<SheetTitle>{title}</SheetTitle>
						<SheetDescription>仅追加更正事件，原始成交证据不会修改；最终有效状态由后端重新计算。</SheetDescription>
					</SheetHeader>
					<OriginalFillEvidence fill={fill} />
					<div className="rounded-(--radius-sm) bg-(--color-surface-strip) px-3 py-2 text-xs text-(--color-foreground-secondary)">
						<span className="block text-(--color-foreground-secondary)">更正事件 ID</span>
						<span className="block truncate font-data text-(--color-foreground-secondary)" title={ids.adjustmentId}>
							{ids.adjustmentId}
						</span>
						{kind === "replace" && (
							<>
								<span className="mt-1 block text-(--color-foreground-secondary)">替换成交 ID</span>
								<span
									className="block truncate font-data text-(--color-foreground-secondary)"
									title={ids.replacementFillId}
								>
									{ids.replacementFillId}
								</span>
							</>
						)}
					</div>
					<FillCorrectionFields
						form={form}
						showReplacement={kind === "replace"}
						disabled={isLocked}
						onChange={updateForm}
					/>
					{errorMessage && (
						<p
							role="alert"
							className="rounded-(--radius-sm) bg-(--color-status-led-error)/8 px-2 py-1.5 text-(length:--text-sm) text-(--color-status-led-error)"
						>
							{errorMessage}
						</p>
					)}
					<SheetFooter className="mt-auto">
						<Button
							type="button"
							variant="outline"
							disabled={mustPreserveCommand}
							onClick={() => handleOpenChange(false)}
						>
							取消
						</Button>
						{isConflict && (
							<Button type="button" variant="secondary" onClick={closeAndRefresh}>
								关闭并刷新流水
							</Button>
						)}
						{canRetry ? (
							<Button type="button" onClick={() => execute(lastCommand)}>
								使用同一标识重试
							</Button>
						) : !isConflict ? (
							<Button type="submit" disabled={mutation.isPending}>
								{mutation.isPending ? "追加中" : `确认追加${action}`}
							</Button>
						) : null}
					</SheetFooter>
				</form>
			</SheetContent>
		</Sheet>
	);
}
