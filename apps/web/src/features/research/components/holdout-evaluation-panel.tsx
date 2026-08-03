import { useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import type { CandidateSelectionReceiptResponse } from "../api/experiments";
import { useHoldoutEvaluation } from "../hooks";

interface HoldoutEvaluationPanelProps {
	readonly selection: CandidateSelectionReceiptResponse;
	readonly expectedFoldRevision: number;
}

function key(): string {
	return `holdout-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

export function HoldoutEvaluationPanel({ selection, expectedFoldRevision }: HoldoutEvaluationPanelProps) {
	const mutation = useHoldoutEvaluation();
	const commandKey = useRef<string | null>(null);
	const [blocked, setBlocked] = useState(false);

	function evaluate(): void {
		commandKey.current ??= key();
		mutation.mutate(
			{
				experimentId: selection.experiment_id,
				idempotencyKey: commandKey.current,
				request: {
					candidate_id: selection.candidate_id,
					selection_id: selection.selection_id,
					expected_selection_evidence_hash: selection.selection_evidence_content_hash,
					expected_candidate_evidence_content_hash: selection.candidate_evidence_content_hash,
					expected_revision: expectedFoldRevision,
					operator_confirmation: "operator reviewed immutable candidate and selection evidence",
					selection_reason: { code: "objective_review", summary: "candidate won the registered objective review" },
				},
			},
			{
				onSuccess: () => {
					commandKey.current = null;
					setBlocked(true);
				},
				onError: (error) => {
					if (error instanceof ApiError && error.errorCode === "HOLDOUT_ALREADY_CLAIMED") setBlocked(true);
				},
			},
		);
	}

	const error =
		mutation.error instanceof ApiError
			? `${mutation.error.status} ${mutation.error.errorCode ?? "HOLDOUT_ERROR"}: ${mutation.error.message}`
			: mutation.error?.message;
	return (
		<div className="flex flex-col gap-2 border-t border-(--color-border-subtle) pt-2">
			<p className="font-data text-xs">selection {selection.selection_id}</p>
			<button
				type="button"
				onClick={evaluate}
				disabled={blocked || mutation.isPending}
				className="self-start rounded-(--radius-sm) bg-(--brand-accent) px-2 py-1 text-xs text-(--brand-accent-fg) disabled:opacity-50"
			>
				执行一次性 Holdout
			</button>
			{mutation.data && <p className="font-data text-xs">claim {mutation.data.claim_id}</p>}
			{error && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{error}
				</p>
			)}
		</div>
	);
}
