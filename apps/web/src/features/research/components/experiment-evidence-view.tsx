import type { ExperimentArtifactResponse, ExperimentSelectionEvidenceResponse } from "../api/experiments";

interface ExperimentEvidenceViewProps {
	readonly artifacts: readonly ExperimentArtifactResponse[];
	readonly selectionEvidence: ExperimentSelectionEvidenceResponse | null;
}

export function ExperimentEvidenceView({ artifacts, selectionEvidence }: ExperimentEvidenceViewProps) {
	return (
		<div className="flex flex-col gap-3">
			<div className="overflow-hidden rounded-(--radius-sm) border border-(--color-border-subtle)">
				{artifacts.map((artifact) => (
					<div
						key={artifact.artifact_id}
						className="grid gap-2 border-b border-(--color-border-subtle) px-3 py-2 text-xs last:border-b-0 sm:grid-cols-[12rem_12rem_1fr]"
					>
						<strong className="font-data">{artifact.artifact_id}</strong>
						<span>{artifact.artifact_kind}</span>
						<code className="break-all text-(--color-foreground-secondary)">{artifact.content_hash}</code>
					</div>
				))}
				{artifacts.length === 0 && (
					<p className="px-3 py-4 text-xs text-(--color-foreground-tertiary)">尚未发布固定产物。</p>
				)}
			</div>
			{selectionEvidence ? (
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-2">
					<p className="font-data text-xs break-all">
						{selectionEvidence.artifact_id} · {selectionEvidence.content_hash}
					</p>
					<details className="mt-2 text-xs">
						<summary className="cursor-pointer text-(--color-foreground-secondary)">查看 selection payload</summary>
						<code className="mt-2 block break-all border-t border-(--color-border-subtle) pt-2">
							{JSON.stringify(selectionEvidence.payload)}
						</code>
					</details>
				</div>
			) : (
				<p className="text-xs text-(--color-foreground-tertiary)">Selection evidence 尚未发布。</p>
			)}
		</div>
	);
}
