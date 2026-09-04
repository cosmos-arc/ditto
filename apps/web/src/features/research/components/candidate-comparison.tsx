import { useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import type { CandidateSelectionReceiptResponse } from "../api/experiments";
import { useCandidateSelection } from "../hooks";
import { HoldoutEvaluationPanel } from "./holdout-evaluation-panel";

interface CandidateComparisonProps {
	readonly experimentId: string;
	readonly revision: number;
	readonly candidates: readonly components["schemas"]["ExperimentCandidateResponse"][];
	readonly comparison: components["schemas"]["ExperimentComparisonResponse"] | null;
	readonly selectionEvidenceReady: boolean;
	readonly selectionState: components["schemas"]["ExperimentSelectionStateResponse"] | null;
	readonly onInspect?: (candidateId: string) => void;
}

function key(): string {
	return `candidate-selection-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

export function CandidateComparison({
	experimentId,
	revision,
	candidates,
	comparison,
	selectionEvidenceReady,
	selectionState,
	onInspect,
}: CandidateComparisonProps) {
	const [pinned, setPinned] = useState<string[]>([]);
	const [rationale, setRationale] = useState("");
	const [localSelection, setLocalSelection] = useState<CandidateSelectionReceiptResponse | null>(null);
	const selection = localSelection ?? selectionState;
	const mutation = useCandidateSelection();
	const attempts = useRef(new Map<string, string>());

	function toggle(candidateId: string): void {
		setPinned((current) =>
			current.includes(candidateId)
				? current.filter((id) => id !== candidateId)
				: current.length < 4
					? [...current, candidateId]
					: current,
		);
	}

	function select(candidateId: string): void {
		if (selection || !selectionEvidenceReady || !comparison || comparison.revision !== revision || !rationale.trim())
			return;
		const identity = `${candidateId}:${comparison.payload_hash}:${revision}:${rationale.trim()}`;
		const idempotencyKey = attempts.current.get(identity) ?? key();
		attempts.current.set(identity, idempotencyKey);
		mutation.mutate(
			{
				experimentId,
				idempotencyKey,
				request: {
					candidate_id: candidateId,
					rationale: rationale.trim(),
					comparison_payload_hash: comparison.payload_hash,
					expected_revision: comparison.revision,
				},
			},
			{
				onSuccess: (receipt) => {
					attempts.current.delete(identity);
					setLocalSelection(receipt);
				},
			},
		);
	}

	const error =
		mutation.error instanceof ApiError
			? `${mutation.error.status} ${mutation.error.errorCode ?? "CANDIDATE_SELECTION_ERROR"}: ${mutation.error.message}`
			: mutation.error?.message;
	return (
		<div className="flex flex-col gap-3">
			{comparison && !selectionEvidenceReady && (
				<p role="status" className="text-xs text-(--color-foreground-secondary)">
					Selection evidence is publishing; candidate promotion remains locked.
				</p>
			)}
			<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
				<span>晋级理由</span>
				<input
					aria-label="晋级理由"
					value={rationale}
					onChange={(e) => setRationale(e.target.value)}
					className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1"
				/>
			</label>
			<div className="overflow-hidden rounded-(--radius-sm) border border-(--color-border-subtle)">
				<div className="hidden grid-cols-[24px_150px_minmax(0,1fr)_72px_72px] gap-2 bg-(--color-surface-strip) px-3 py-1.5 text-xs uppercase tracking-[0.06em] text-(--color-foreground-tertiary) sm:grid">
					<span>Pin</span>
					<span>Candidate</span>
					<span>Parameters</span>
					<span>Evidence</span>
					<span>Promotion</span>
				</div>
				<div className="divide-y divide-(--color-border-subtle)">
					{candidates.map((candidate) => {
						const isPinned = pinned.includes(candidate.candidate_id);
						return (
							<div
								key={candidate.candidate_id}
								className="grid gap-2 px-3 py-2 text-xs transition-colors hover:bg-(--color-interaction-hover-subtle-bg) sm:grid-cols-[24px_150px_minmax(0,1fr)_72px_72px] sm:items-center"
							>
								<input
									type="checkbox"
									aria-label={`Pin ${candidate.candidate_id}`}
									checked={isPinned}
									disabled={!isPinned && pinned.length >= 4}
									onChange={() => toggle(candidate.candidate_id)}
								/>
								<strong className="font-data font-medium">{candidate.candidate_id}</strong>
								<code className="min-w-0 truncate text-(--color-foreground-secondary)">
									{JSON.stringify(candidate.parameters)}
								</code>
								<button
									type="button"
									onClick={() => onInspect?.(candidate.candidate_id)}
									className="text-left text-(--color-accent) hover:underline"
								>
									查看证据
								</button>
								<button
									type="button"
									aria-label={`选择为晋级候选 ${candidate.candidate_id}`}
									data-candidate-role={candidate.is_baseline ? "baseline" : "eligible"}
									disabled={
										!selectionEvidenceReady ||
										!comparison ||
										comparison.revision !== revision ||
										candidate.is_baseline ||
										!isPinned ||
										!rationale.trim() ||
										selection !== null ||
										mutation.isPending
									}
									onClick={() => select(candidate.candidate_id)}
									className="rounded-(--radius-sm) border border-(--color-border-strong) px-2 py-1 text-(--color-foreground-secondary) disabled:opacity-50"
								>
									晋级
								</button>
							</div>
						);
					})}
				</div>
			</div>
			{comparison && (
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-2">
					<p className="font-data text-xs break-all">
						<span className="text-(--color-foreground-tertiary)">COMPARISON</span> {comparison.payload_hash} · revision{" "}
						{comparison.revision}
					</p>
					<details className="mt-2 text-xs">
						<summary className="cursor-pointer text-(--color-foreground-secondary)">查看比较载荷</summary>
						<code className="mt-2 block break-all border-t border-(--color-border-subtle) pt-2">
							{JSON.stringify(comparison.payload)}
						</code>
					</details>
				</div>
			)}
			{error && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{error}
				</p>
			)}
			{selection && (
				<HoldoutEvaluationPanel selection={selection} existingClaimId={selectionState?.holdout_claim_id ?? null} />
			)}
		</div>
	);
}
