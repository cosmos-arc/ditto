import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import type { ReactivateVariables } from "../hooks/use-strategy-governance";
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
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>{title}</DialogTitle>
					{description ? <DialogDescription>{description}</DialogDescription> : null}
				</DialogHeader>
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
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
						取消
					</Button>
					<Button onClick={handleConfirm} disabled={!canConfirm}>
						{isPending ? "处理中…" : confirmLabel}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

interface ReactivateDialogProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly targetVersion: number;
	readonly expectedPointerRevision: number;
	readonly isPending: boolean;
	readonly onConfirm: (variables: ReactivateVariables) => void;
}

/** 重新激活 dialog（乐观指针 CAS + type-to-confirm）。 */
export function ReactivateDialog({
	open,
	onOpenChange,
	targetVersion,
	expectedPointerRevision,
	isPending,
	onConfirm,
}: ReactivateDialogProps): ReactElement {
	const [actor, setActor] = useState("");
	const [reason, setReason] = useState("");
	const [impactSummary, setImpactSummary] = useState("");
	const [confirmation, setConfirmation] = useState("");

	const expectedConfirmation = `重新激活 v${targetVersion}`;

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

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>重新激活 v{targetVersion}</DialogTitle>
					<DialogDescription>
						乐观指针 CAS：要求 expected_pointer_revision={expectedPointerRevision}（最后读到的 active 指针版本）。
					</DialogDescription>
				</DialogHeader>
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
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
						取消
					</Button>
					<Button onClick={handleConfirm} disabled={!canConfirm}>
						{isPending ? "处理中…" : "确认重新激活"}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
