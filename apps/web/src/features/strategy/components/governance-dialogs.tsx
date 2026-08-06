import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ApiError } from "@/lib/api-client";
import type { PublishVariables, ReactivateVariables } from "../hooks/use-strategy-governance";
import { INPUT_CLASS, TextField } from "./spec-fields";

interface DecisionDialogProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly title: string;
	readonly description?: string;
	readonly confirmLabel: string;
	readonly isPending: boolean;
	readonly onConfirm: (actor: string, reason: string) => void;
}

/** 治理决策 dialog（submit/approve/reject/deprecate）：actor + reason 必填才启用确认。 */
export function DecisionDialog({
	open,
	onOpenChange,
	title,
	description,
	confirmLabel,
	isPending,
	onConfirm,
}: DecisionDialogProps): ReactElement {
	const [actor, setActor] = useState("");
	const [reason, setReason] = useState("");

	useEffect(() => {
		if (!open) {
			setActor("");
			setReason("");
		}
	}, [open]);

	const canConfirm = actor.trim() !== "" && reason.trim() !== "" && !isPending;

	function handleConfirm(): void {
		if (!canConfirm) return;
		onConfirm(actor.trim(), reason.trim());
	}

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>{title}</SheetTitle>
					{description ? <SheetDescription>{description}</SheetDescription> : null}
				</SheetHeader>
				<div className="flex flex-col gap-3">
					<TextField label="执行者" value={actor} onChange={setActor} />
					<label className="flex flex-col gap-1 text-(length:--text-sm)">
						<span className="text-(--color-foreground-secondary)">原因</span>
						<textarea
							aria-label="原因"
							className={INPUT_CLASS}
							rows={3}
							value={reason}
							onChange={(event) => setReason(event.target.value)}
						/>
					</label>
				</div>
				<SheetFooter className="mt-auto">
					<Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
						取消
					</Button>
					<Button onClick={handleConfirm} disabled={!canConfirm}>
						{isPending ? "处理中…" : confirmLabel}
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

interface ReactivateDialogProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly strategyId: string;
	readonly currentActiveVersion: number | null;
	readonly targetVersion: number;
	readonly expectedPointerRevision: number;
	readonly isPending: boolean;
	readonly onConfirm: (variables: ReactivateVariables) => void;
	readonly error?: Error | null;
}

/** 构造后端要求的、绑定策略版本与 active pointer revision 的精确确认串。 */
export function reactivateConfirmation(strategyId: string, version: number, pointerRevision: number): string {
	return `strategy:reactivate:${strategyId}@${version}:pointer-revision:${pointerRevision}:confirm`;
}

/** 重新激活 dialog（乐观指针 CAS + type-to-confirm）。 */
export function ReactivateDialog({
	open,
	onOpenChange,
	strategyId,
	currentActiveVersion,
	targetVersion,
	expectedPointerRevision,
	isPending,
	onConfirm,
	error,
}: ReactivateDialogProps): ReactElement {
	const [actor, setActor] = useState("");
	const [reason, setReason] = useState("");
	const [impactSummary, setImpactSummary] = useState("");
	const [confirmation, setConfirmation] = useState("");

	const expectedConfirmation = reactivateConfirmation(strategyId, targetVersion, expectedPointerRevision);

	useEffect(() => {
		if (!open) {
			setActor("");
			setReason("");
			setImpactSummary("");
			setConfirmation("");
		}
	}, [open]);

	const confirmationMatched = confirmation.trim() === expectedConfirmation;
	const canConfirm =
		actor.trim() !== "" && reason.trim() !== "" && impactSummary.trim() !== "" && confirmationMatched && !isPending;

	function handleConfirm(): void {
		if (!canConfirm) return;
		onConfirm({
			version: targetVersion,
			actor: actor.trim(),
			reason: reason.trim(),
			confirmation: confirmation.trim(),
			impactSummary: impactSummary.trim(),
			expectedPointerRevision,
		});
	}

	function handleOpenChange(nextOpen: boolean): void {
		if (!nextOpen && isPending) return;
		onOpenChange(nextOpen);
	}

	return (
		<Sheet open={open} onOpenChange={handleOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>重新激活 v{targetVersion}</SheetTitle>
					<SheetDescription>
						current v{currentActiveVersion ?? "—"} → target v{targetVersion} · pointer revision{" "}
						{expectedPointerRevision}
					</SheetDescription>
				</SheetHeader>
				<div className="flex flex-col gap-3">
					<TextField label="执行者" value={actor} onChange={setActor} />
					<TextField label="原因" value={reason} onChange={setReason} />
					<TextField label="影响摘要" value={impactSummary} onChange={setImpactSummary} />
					<label className="flex flex-col gap-1 text-(length:--text-sm)">
						<span className="text-(--color-foreground-secondary)">确认句（输入「{expectedConfirmation}」以启用）</span>
						<input
							aria-label="确认句"
							className={INPUT_CLASS}
							value={confirmation}
							onChange={(event) => setConfirmation(event.target.value)}
						/>
					</label>
				</div>
				{error && (
					<p role="alert" className="text-xs text-(--color-led-danger)">
						{error instanceof ApiError
							? `${error.status} ${error.errorCode ?? "REACTIVATE_ERROR"}: ${error.message}`
							: error.message}
					</p>
				)}
				<SheetFooter className="mt-auto">
					<Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
						取消
					</Button>
					<Button onClick={handleConfirm} disabled={!canConfirm}>
						{isPending ? "处理中…" : "确认重新激活"}
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

interface PublishDialogProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly targetVersion: number;
	readonly bundleHash: string;
	readonly isPending: boolean;
	readonly onConfirm: (variables: PublishVariables) => void;
}

/**
 * 发布 dialog（evidence-gated：review packet 的 bundle_hash 作为证据身份 +
 * type-to-confirm「发布 vN」）。bundle_hash 只读展示，确认句匹配才启用。
 */
export function PublishDialog({
	open,
	onOpenChange,
	targetVersion,
	bundleHash,
	isPending,
	onConfirm,
}: PublishDialogProps): ReactElement {
	const [actor, setActor] = useState("");
	const [reason, setReason] = useState("");
	const [confirmation, setConfirmation] = useState("");

	const expectedConfirmation = `发布 v${targetVersion}`;

	useEffect(() => {
		if (!open) {
			setActor("");
			setReason("");
			setConfirmation("");
		}
	}, [open]);

	const confirmationMatched = confirmation.trim() === expectedConfirmation;
	const canConfirm = actor.trim() !== "" && reason.trim() !== "" && confirmationMatched && !isPending;

	function handleConfirm(): void {
		if (!canConfirm) return;
		onConfirm({ version: targetVersion, bundleHash, actor: actor.trim(), reason: reason.trim() });
	}

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>发布 v{targetVersion}</SheetTitle>
					<SheetDescription>
						evidence-gated：使用 review packet 的 bundle_hash 作为证据身份，后端重新加载 packet 并执行 hard gate。
					</SheetDescription>
				</SheetHeader>
				<div className="flex flex-col gap-3">
					<div className="flex items-center justify-between gap-2 text-xs">
						<span className="text-(--color-foreground-tertiary)">bundle_hash（证据）</span>
						<code className="font-mono text-(--color-foreground-secondary)" title={bundleHash}>
							{bundleHash.slice(0, 12)}…{bundleHash.slice(-8)}
						</code>
					</div>
					<TextField label="执行者" value={actor} onChange={setActor} />
					<label className="flex flex-col gap-1 text-(length:--text-sm)">
						<span className="text-(--color-foreground-secondary)">原因</span>
						<textarea
							aria-label="原因"
							className={INPUT_CLASS}
							rows={3}
							value={reason}
							onChange={(event) => setReason(event.target.value)}
						/>
					</label>
					<label className="flex flex-col gap-1 text-(length:--text-sm)">
						<span className="text-(--color-foreground-secondary)">确认句（输入「{expectedConfirmation}」以启用）</span>
						<input
							aria-label="确认句"
							className={INPUT_CLASS}
							value={confirmation}
							onChange={(event) => setConfirmation(event.target.value)}
						/>
					</label>
				</div>
				<SheetFooter className="mt-auto">
					<Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
						取消
					</Button>
					<Button onClick={handleConfirm} disabled={!canConfirm}>
						{isPending ? "处理中…" : "确认发布"}
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}
