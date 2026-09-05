import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	dataProductOperationsKeys,
	decideRemediationApproval,
	draftFallbackPolicy,
	executeRemediationApproval,
	fetchFallbackPolicies,
	fetchFallbackPreview,
	fetchFallbackSummary,
	fetchPromotionHistory,
	fetchPromotionReadiness,
	fetchRemediationApprovals,
	fetchRemediationBacklog,
	fetchRemediationDetail,
	fetchSourceHealth,
	fetchSourceHealthSummary,
	requestRemediationApproval,
	revokePromotion,
	transitionFallbackPolicy,
} from "../api/operations";
import type {
	DataProductOperationsScope,
	FallbackPreviewView,
	TransitionFallbackPolicyCommand,
} from "../types/operations";

const OPERATIONS_STALE_TIME_MS = 30_000;

export function useDataProductOperations(scope: DataProductOperationsScope, selectedRemediationItemId = "") {
	const enabled = scope.datasetId.length > 0 && scope.tradeDate.length > 0;
	const remediation = useQuery({
		queryKey: dataProductOperationsKeys.remediation(scope.datasetId, scope.tradeDate),
		queryFn: () => fetchRemediationBacklog(scope),
		enabled,
		placeholderData: keepPreviousData,
		staleTime: OPERATIONS_STALE_TIME_MS,
	});
	const remediationItemId =
		remediation.data?.items.find((item) => item.itemId === selectedRemediationItemId)?.itemId ??
		remediation.data?.items[0]?.itemId ??
		"";
	return {
		approvals: useQuery({
			queryKey: dataProductOperationsKeys.approvals(scope.datasetId),
			queryFn: () => fetchRemediationApprovals(scope.datasetId),
			enabled,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		fallbackPolicies: useQuery({
			queryKey: dataProductOperationsKeys.fallbackPolicies(scope.datasetId),
			queryFn: () => fetchFallbackPolicies(scope.datasetId),
			enabled,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		fallbackPreview: useQuery({
			queryKey: dataProductOperationsKeys.fallbackPreview(scope.datasetId, scope.tradeDate),
			queryFn: () => fetchFallbackPreview(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		fallbackSummary: useQuery({
			queryKey: dataProductOperationsKeys.fallbackSummary(scope.datasetId, scope.tradeDate),
			queryFn: () => fetchFallbackSummary(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		promotion: useQuery({
			queryKey: dataProductOperationsKeys.promotion(scope.datasetId, scope.tradeDate),
			queryFn: () => fetchPromotionReadiness(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		promotionHistory: useQuery({
			queryKey: dataProductOperationsKeys.promotionHistory(scope.datasetId),
			queryFn: () => fetchPromotionHistory(scope.datasetId),
			enabled,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		remediation,
		remediationDetail: useQuery({
			queryKey: dataProductOperationsKeys.remediationDetail(scope.datasetId, scope.tradeDate, remediationItemId),
			queryFn: () => fetchRemediationDetail(remediationItemId, scope),
			enabled: enabled && remediationItemId.length > 0,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		sourceHealth: useQuery({
			queryKey: dataProductOperationsKeys.sourceHealth(scope.datasetId, scope.tradeDate),
			queryFn: () => fetchSourceHealth(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
		sourceHealthSummary: useQuery({
			queryKey: dataProductOperationsKeys.sourceHealthSummary(scope.datasetId, scope.tradeDate),
			queryFn: () => fetchSourceHealthSummary(scope),
			enabled,
			placeholderData: keepPreviousData,
			staleTime: OPERATIONS_STALE_TIME_MS,
		}),
	};
}

function useInvalidateOperations(queryKeys: readonly (readonly unknown[])[]) {
	const queryClient = useQueryClient();
	return () => {
		for (const queryKey of queryKeys) void queryClient.invalidateQueries({ queryKey });
	};
}

export function useRequestRemediationApproval(datasetId: string) {
	const invalidate = useInvalidateOperations([dataProductOperationsKeys.approvals(datasetId)]);
	return useMutation({ mutationFn: requestRemediationApproval, onSuccess: invalidate });
}

export function useDecideRemediationApproval(datasetId: string) {
	const invalidate = useInvalidateOperations([dataProductOperationsKeys.approvals(datasetId)]);
	return useMutation({ mutationFn: decideRemediationApproval, onSuccess: invalidate });
}

export function useExecuteRemediationApproval(datasetId: string, tradeDate: string) {
	const invalidate = useInvalidateOperations([
		dataProductOperationsKeys.approvals(datasetId),
		dataProductOperationsKeys.remediation(datasetId, tradeDate),
		dataProductOperationsKeys.sourceHealth(datasetId, tradeDate),
		dataProductOperationsKeys.promotion(datasetId, tradeDate),
	]);
	return useMutation({ mutationFn: executeRemediationApproval, onSuccess: invalidate });
}

export function useDraftFallbackPolicy(datasetId: string) {
	const invalidate = useInvalidateOperations([dataProductOperationsKeys.fallbackPolicies(datasetId)]);
	return useMutation({
		mutationFn: ({ preview, createdBy }: { readonly preview: FallbackPreviewView; readonly createdBy: string }) =>
			draftFallbackPolicy(preview, createdBy),
		onSuccess: invalidate,
	});
}

export function useTransitionFallbackPolicy(datasetId: string, tradeDate: string) {
	const invalidate = useInvalidateOperations([
		dataProductOperationsKeys.fallbackPolicies(datasetId),
		dataProductOperationsKeys.fallbackPreview(datasetId, tradeDate),
		dataProductOperationsKeys.fallbackSummary(datasetId, tradeDate),
		dataProductOperationsKeys.sourceHealth(datasetId, tradeDate),
	]);
	return useMutation({
		mutationFn: (command: TransitionFallbackPolicyCommand) => transitionFallbackPolicy(command),
		onSuccess: invalidate,
	});
}

export function useRevokePromotion(datasetId: string, tradeDate: string) {
	const invalidate = useInvalidateOperations([
		dataProductOperationsKeys.promotion(datasetId, tradeDate),
		dataProductOperationsKeys.promotionHistory(datasetId),
		dataProductOperationsKeys.sourceHealth(datasetId, tradeDate),
	]);
	return useMutation({ mutationFn: revokePromotion, onSuccess: invalidate });
}
