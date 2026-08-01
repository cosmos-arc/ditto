import type { components } from "@/types/generated/api";

interface ExperimentEvidenceViewProps {
	readonly artifacts: readonly components["schemas"]["ExperimentArtifactResponse"][];
	readonly selectionEvidence: components["schemas"]["ExperimentSelectionEvidenceResponse"] | null;
}

export function ExperimentEvidenceView({ artifacts, selectionEvidence }: ExperimentEvidenceViewProps) {
	return (
		<div className="flex flex-col gap-3">
			<div className="divide-y divide-(--color-border-subtle)">
				{artifacts.map((artifact) => (
					<div key={artifact.artifact_id} className="grid gap-1 py-2 text-xs sm:grid-cols-[12rem_10rem_1fr]">
						<strong>{artifact.artifact_id}</strong>
						<span>{artifact.artifact_kind}</span>
						<code className="break-all">{artifact.content_hash}</code>
					</div>
				))}
			</div>
			{selectionEvidence && (
				<div>
					<p className="font-data text-xs break-all">
						{selectionEvidence.artifact_id} · {selectionEvidence.content_hash}
					</p>
					<code className="block break-all text-xs">{JSON.stringify(selectionEvidence.payload)}</code>
				</div>
			)}
		</div>
	);
}
