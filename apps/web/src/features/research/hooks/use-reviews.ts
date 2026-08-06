/**
 * useReviews —— review queue（待审查 / 已批准待发布版本）.
 *
 * 数据来自 `GET /v1/research/reviews`，mapper 在 queryFn 内翻译为 view-model。
 */
import { useQuery } from "@tanstack/react-query";
import { reviewKeys } from "../api/query-keys";
import { fetchReviews, mapReviewQueueEntry } from "../api/reviews";

export function useReviews() {
	return useQuery({
		queryKey: reviewKeys.list(),
		queryFn: () => fetchReviews().then((entries) => entries.map(mapReviewQueueEntry)),
	});
}
