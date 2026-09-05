import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export type CandidateEvidenceResourceKind = "selections" | "exclusions" | "factor-contributions";
type SelectionPage = components["schemas"]["CandidateSelectionPageResponse"];
type ExclusionPage = components["schemas"]["CandidateExclusionPageResponse"];
type ContributionPage = components["schemas"]["CandidateFactorContributionPageResponse"];
type CandidateEvidenceDto = SelectionPage | ExclusionPage | ContributionPage;

export type CandidateEvidencePage = {
	readonly candidateId: string;
	readonly experimentId: string;
	readonly candidateBundleArtifactId: string;
	readonly contentHash: string;
	readonly resourceKind: CandidateEvidenceResourceKind;
	readonly items: readonly Readonly<Record<string, unknown>>[];
	readonly nextCursor: string | null;
};

export type CandidateEvidenceCursor = {
	readonly cursor: string;
	readonly candidateId: string;
	readonly experimentId: string;
	readonly candidateBundleArtifactId: string;
	readonly contentHash: string;
	readonly resourceKind: CandidateEvidenceResourceKind;
};

export async function fetchCandidateEvidencePage(
	experimentId: string,
	candidateId: string,
	resourceKind: CandidateEvidenceResourceKind,
	cursor: CandidateEvidenceCursor | null,
): Promise<CandidateEvidencePage> {
	if (
		cursor &&
		(cursor.experimentId !== experimentId || cursor.candidateId !== candidateId || cursor.resourceKind !== resourceKind)
	) {
		throw new Error("INVALID_CANDIDATE_EVIDENCE_CURSOR: cursor identity does not match resource scope");
	}
	const params = {
		path: { candidate_id: candidateId },
		query: { experiment_id: experimentId, ...(cursor ? { cursor: cursor.cursor } : {}), limit: 20 },
	};
	const dto: CandidateEvidenceDto =
		resourceKind === "selections"
			? await apiClient.get("/api/v1/research/candidates/{candidate_id}/selections", { params })
			: resourceKind === "exclusions"
				? await apiClient.get("/api/v1/research/candidates/{candidate_id}/exclusions", { params })
				: await apiClient.get("/api/v1/research/candidates/{candidate_id}/factor-contributions", { params });
	if (
		dto.experiment_id !== experimentId ||
		dto.candidate_id !== candidateId ||
		(cursor && (dto.artifact_id !== cursor.candidateBundleArtifactId || dto.content_hash !== cursor.contentHash))
	) {
		throw new Error("EVIDENCE_STALE: candidate bundle identity changed while paging");
	}
	return {
		candidateId: dto.candidate_id,
		experimentId: dto.experiment_id,
		candidateBundleArtifactId: dto.artifact_id,
		contentHash: dto.content_hash,
		resourceKind,
		items: dto.items.map((item) => ({ ...item })),
		nextCursor: dto.next_cursor,
	};
}

export function nextCandidateEvidenceCursor(page: CandidateEvidencePage): CandidateEvidenceCursor | null {
	if (!page.nextCursor) return null;
	return {
		cursor: page.nextCursor,
		candidateId: page.candidateId,
		experimentId: page.experimentId,
		candidateBundleArtifactId: page.candidateBundleArtifactId,
		contentHash: page.contentHash,
		resourceKind: page.resourceKind,
	};
}
