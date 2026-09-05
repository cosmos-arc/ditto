import { useRef, useState } from "react";
import { ApiError } from "@/api";
import type {
	ExperimentControlAction,
	ExperimentControlReceiptResponse,
	ExperimentDetailResponse,
	ExperimentFoldResponse,
} from "../api/experiments";
import { useExperimentControl, useExperimentRetryFold } from "../hooks";

interface ExperimentRunControlsProps {
	readonly detail: ExperimentDetailResponse;
}

function idempotencyKey(prefix: string): string {
	const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
	return `${prefix}-${random}`;
}

function typedError(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "EXPERIMENT_CONTROL_ERROR"}: ${error.message}`
		: error.message;
}

export function ExperimentRunControls({ detail }: ExperimentRunControlsProps) {
	const control = useExperimentControl();
	const retry = useExperimentRetryFold();
	const [receipt, setReceipt] = useState<ExperimentControlReceiptResponse | null>(null);
	const attempts = useRef(new Map<string, string>());
	const status = detail.status.toLowerCase();
	const actions: ExperimentControlAction[] =
		status === "running"
			? ["pause", "cancel"]
			: status === "paused"
				? ["resume", "cancel"]
				: status === "queued"
					? ["cancel"]
					: [];

	function commandKey(identity: string): string {
		const existing = attempts.current.get(identity);
		if (existing) return existing;
		const key = idempotencyKey("experiment-control");
		attempts.current.set(identity, key);
		return key;
	}

	function mutate(action: ExperimentControlAction): void {
		const identity = `${action}:${detail.revision}`;
		control.mutate(
			{
				experimentId: detail.experiment_id,
				action,
				expectedRevision: detail.revision,
				idempotencyKey: commandKey(identity),
			},
			{
				onSuccess: (next) => {
					attempts.current.delete(identity);
					setReceipt(next);
				},
			},
		);
	}

	function retryFold(fold: ExperimentFoldResponse): void {
		const identity = `retry:${fold.fold_id}:${fold.revision}`;
		retry.mutate(
			{
				experimentId: detail.experiment_id,
				candidateId: fold.candidate_id,
				foldId: fold.fold_id,
				expectedRevision: fold.revision,
				idempotencyKey: commandKey(identity),
			},
			{
				onSuccess: (next) => {
					attempts.current.delete(identity);
					setReceipt(next);
				},
			},
		);
	}

	const labels: Record<ExperimentControlAction, string> = { pause: "暂停", cancel: "取消", resume: "恢复" };
	return (
		<div className="flex flex-col gap-2">
			<div className="flex flex-wrap gap-2">
				{actions.map((action) => (
					<button
						key={action}
						type="button"
						disabled={control.isPending}
						onClick={() => mutate(action)}
						className="rounded-(--radius-sm) border border-(--color-border-strong) px-2 py-1 text-xs disabled:opacity-50"
					>
						{labels[action]}
					</button>
				))}
				{detail.folds
					.filter((fold) => fold.status.toLowerCase() === "failed")
					.map((fold) => (
						<button
							key={fold.fold_id}
							type="button"
							disabled={retry.isPending}
							onClick={() => retryFold(fold)}
							className="rounded-(--radius-sm) border border-(--color-border-strong) px-2 py-1 text-xs disabled:opacity-50"
						>
							重试 {fold.fold_id}
						</button>
					))}
			</div>
			{receipt && (
				<p className="font-data text-xs text-(--color-foreground-secondary)">
					{receipt.status} · revision {receipt.revision}
				</p>
			)}
			{typedError(control.error) && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{typedError(control.error)}
				</p>
			)}
			{typedError(retry.error) && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{typedError(retry.error)}
				</p>
			)}
		</div>
	);
}
