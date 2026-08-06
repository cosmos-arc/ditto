/**
 * useReviewPacket —— 一个 experiment 的完整 review packet read model.
 *
 * 数据来自 `GET /v1/research/experiments/{id}/review-packet`。`enabled` 由调用方
 * 按 experimentId 是否可用门控（review queue 项 experimentId 为 null 时禁用）。
 */
import { useQuery } from "@tanstack/react-query";
import { reviewKeys } from "../api/query-keys";
import { fetchReviewPacket, mapReviewPacket } from "../api/review-packet";

export function useReviewPacket(experimentId: string | null | undefined) {
	return useQuery({
		queryKey: reviewKeys.packet(experimentId ?? ""),
		queryFn: () => fetchReviewPacket(experimentId as string).then(mapReviewPacket),
		enabled: experimentId != null && experimentId !== "",
	});
}
