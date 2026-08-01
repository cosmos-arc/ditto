import { useInfiniteQuery } from "@tanstack/react-query";
import {
	type CandidateEvidenceCursor,
	type CandidateEvidenceResourceKind,
	fetchCandidateEvidencePage,
	nextCandidateEvidenceCursor,
} from "../api/candidate-evidence";
import { experimentKeys } from "../api/query-keys";

export function useCandidateEvidence(
	experimentId: string,
	candidateId: string,
	resourceKind: CandidateEvidenceResourceKind,
) {
	return useInfiniteQuery({
		queryKey: experimentKeys.candidateEvidence(experimentId, candidateId, resourceKind),
		queryFn: ({ pageParam }) => fetchCandidateEvidencePage(experimentId, candidateId, resourceKind, pageParam),
		initialPageParam: null as CandidateEvidenceCursor | null,
		getNextPageParam: nextCandidateEvidenceCursor,
		retry: false,
	});
}
