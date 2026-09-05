import { ApiError } from "@/api";
import { ContextActions } from "@/providers";
import type { CandidateEvidenceResourceKind } from "../api/candidate-evidence";
import { useCandidateEvidence } from "../hooks";

interface CandidateEvidenceDrilldownProps {
	readonly experimentId: string;
	readonly candidateId: string;
}

function message(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "CANDIDATE_EVIDENCE_ERROR"}: ${error.message}`
		: error.message;
}

function Resource({
	experimentId,
	candidateId,
	kind,
}: CandidateEvidenceDrilldownProps & { readonly kind: CandidateEvidenceResourceKind }) {
	const query = useCandidateEvidence(experimentId, candidateId, kind);
	const stale =
		query.error &&
		(query.error instanceof ApiError
			? query.error.errorCode === "EVIDENCE_STALE"
			: query.error.message.includes("EVIDENCE_STALE"));
	const pages = stale ? [] : (query.data?.pages ?? []);
	const items = pages.flatMap((page) => page.items);
	return (
		<section className="flex flex-col gap-2 border-t border-(--color-border-subtle) py-2">
			<h4 className="text-xs font-semibold">{kind}</h4>
			{pages[0] && (
				<p className="font-data text-xs break-all">
					{pages[0].candidateBundleArtifactId} · {pages[0].contentHash}
				</p>
			)}
			{query.error && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{message(query.error)}
				</p>
			)}
			{!stale &&
				items.map((item) => (
					<code key={`${kind}-${JSON.stringify(item)}`} className="block break-all text-xs">
						{JSON.stringify(item)}
					</code>
				))}
			{query.hasNextPage && !query.error && (
				<button
					type="button"
					onClick={() => void query.fetchNextPage()}
					disabled={query.isFetchingNextPage}
					className="self-start underline text-xs"
				>
					加载更多 {kind}
				</button>
			)}
		</section>
	);
}

export function CandidateEvidenceDrilldown({ experimentId, candidateId }: CandidateEvidenceDrilldownProps) {
	return (
		<div className="flex flex-col">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<h3 className="text-sm font-semibold">Candidate evidence · {candidateId}</h3>
				<ContextActions
					contextType="experiment-candidate"
					contextId={`${experimentId}:${candidateId}`}
					evidenceObjective="复核候选的选择、排除、因子贡献与 provenance"
				/>
			</div>
			<Resource experimentId={experimentId} candidateId={candidateId} kind="selections" />
			<Resource experimentId={experimentId} candidateId={candidateId} kind="exclusions" />
			<Resource experimentId={experimentId} candidateId={candidateId} kind="factor-contributions" />
		</div>
	);
}
