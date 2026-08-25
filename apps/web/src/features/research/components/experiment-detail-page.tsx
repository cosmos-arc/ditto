import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { AgentContextActions } from "@/features/agent";
import { StatusBar } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import {
	useExperiment,
	useExperimentArtifacts,
	useExperimentCandidates,
	useExperimentComparison,
	useExperimentGates,
	useExperimentSelectionEvidence,
} from "../hooks";
import { CandidateComparison } from "./candidate-comparison";
import { CandidateEvidenceDrilldown } from "./candidate-evidence-drilldown";
import { ExperimentEvidenceView } from "./experiment-evidence-view";
import { ExperimentRunControls } from "./experiment-run-controls";
import { ExperimentValidationView } from "./experiment-validation-view";

interface ExperimentDetailPageProps {
	readonly experimentId: string;
}

function errorText(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "EXPERIMENT_RESOURCE_ERROR"}: ${error.message}`
		: error.message;
}

function ResourceError({ error }: { readonly error: Error | null }) {
	const text = errorText(error);
	return text ? (
		<p role="alert" className="text-xs text-(--color-led-danger)">
			{text}
		</p>
	) : null;
}

export function ExperimentDetailPage({ experimentId }: ExperimentDetailPageProps) {
	const detail = useExperiment(experimentId);
	const candidates = useExperimentCandidates(experimentId);
	const gates = useExperimentGates(experimentId);
	const comparison = useExperimentComparison(experimentId, detail.data?.stage, detail.data?.revision);
	const artifacts = useExperimentArtifacts(experimentId);
	const selection = useExperimentSelectionEvidence(experimentId, detail.data?.stage);
	const [inspectedCandidate, setInspectedCandidate] = useState<string | null>(null);

	if (detail.isLoading) return <LoadingSkeleton variant="panel" />;
	if (!detail.data) return <ResourceError error={detail.error} />;
	const server = detail.data;
	return (
		<>
			<main className="min-h-0 overflow-auto pb-(--height-status-bar)">
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<header
						data-contract-slot="experiment-meta"
						className="flex flex-wrap items-start justify-between gap-3 border-b border-(--color-border-subtle) pb-3"
					>
						<div>
							<h1 className="text-lg font-semibold">Experiment {server.experiment_id}</h1>
							<p className="font-data text-xs">
								{server.status} · {server.stage} · revision {server.revision}
							</p>
						</div>
						<div className="flex flex-wrap items-center justify-end gap-2">
							<AgentContextActions
								contextType="experiment-revision"
								contextId={`${experimentId}@${server.revision}`}
								evidenceObjective="复核当前实验 revision 的候选、门禁、产物与选择证据"
								authorObjective="提出当前实验的结构化变更草案，并保留 frozen identity"
							/>
							<ExperimentRunControls detail={server} />
						</div>
					</header>
					<ContextSection title="Validation and gates">
						<div className="p-(--density-panel-padding)">
							<ResourceError error={gates.error} />
							<ExperimentValidationView folds={server.folds} gates={gates.data ?? []} />
						</div>
					</ContextSection>
					<ContextSection title="Candidate comparison">
						<div className="p-(--density-panel-padding)">
							<ResourceError error={candidates.error} />
							<ResourceError error={comparison.error} />
							<CandidateComparison
								experimentId={experimentId}
								revision={server.revision}
								candidates={candidates.data ?? server.candidates}
								comparison={comparison.data ?? null}
								selectionEvidenceReady={selection.data !== undefined}
								selectionState={server.selection_state}
								onInspect={setInspectedCandidate}
							/>
						</div>
					</ContextSection>
					{inspectedCandidate && (
						<ContextSection title="Candidate drill-down">
							<div className="p-(--density-panel-padding)">
								<CandidateEvidenceDrilldown experimentId={experimentId} candidateId={inspectedCandidate} />
							</div>
						</ContextSection>
					)}
					<ContextSection title="Artifacts and selection evidence">
						<div className="p-(--density-panel-padding)">
							<ResourceError error={artifacts.error} />
							<ResourceError error={selection.error} />
							<ExperimentEvidenceView artifacts={artifacts.data ?? []} selectionEvidence={selection.data ?? null} />
						</div>
					</ContextSection>
				</div>
			</main>
			<StatusBar />
		</>
	);
}
