import { useMutation, useQueryClient } from "@tanstack/react-query";
import { strategyKeys } from "../api/query-keys";
import {
	approveStrategyReview,
	deprecateStrategyVersion,
	reactivateStrategyVersion,
	rejectStrategyReview,
	submitStrategyReview,
} from "../api/strategy-lifecycle";

/** 治理决策动作（submit/approve/reject/deprecate）的公共变量。 */
export type DecisionVariables = {
	readonly version: number;
	readonly actor: string;
	readonly reason: string;
};

/** reactivate 变量（含乐观指针 CAS + 确认句 + 影响摘要）。 */
export type ReactivateVariables = {
	readonly version: number;
	readonly actor: string;
	readonly reason: string;
	readonly confirmation: string;
	readonly impactSummary: string;
	readonly expectedPointerRevision: number;
};

/** 治理 mutation 成功后失效的 scope（版本历史 + active pointer 都会变）。 */
const GOVERNANCE_INVALIDATION_SCOPES = ["versions", "active"] as const;

/**
 * 版本治理 mutations（T20 动作面板数据层）。
 *
 * submit/approve/reject/deprecate 走 `GovernanceDecisionRequest`（actor+reason）；
 * reactivate 额外要求 confirmation + impact_summary + expected_pointer_revision（乐观 CAS）。
 * publish 是 evidence-gated（需 bundle_hash），UI 不直接调用，故不在此 hook 暴露。
 * 所有 mutation 成功后失效 versions + active scope。
 */
export function useStrategyGovernance(strategyId: string) {
	const queryClient = useQueryClient();

	function invalidateGovernedScopes() {
		for (const scope of GOVERNANCE_INVALIDATION_SCOPES) {
			void queryClient.invalidateQueries({ queryKey: [...strategyKeys.all, scope] });
		}
	}

	const submitReview = useMutation({
		mutationFn: ({ version, actor, reason }: DecisionVariables) =>
			submitStrategyReview(strategyId, version, { actor, reason }),
		onSuccess: invalidateGovernedScopes,
	});
	const approve = useMutation({
		mutationFn: ({ version, actor, reason }: DecisionVariables) =>
			approveStrategyReview(strategyId, version, { actor, reason }),
		onSuccess: invalidateGovernedScopes,
	});
	const reject = useMutation({
		mutationFn: ({ version, actor, reason }: DecisionVariables) =>
			rejectStrategyReview(strategyId, version, { actor, reason }),
		onSuccess: invalidateGovernedScopes,
	});
	const deprecate = useMutation({
		mutationFn: ({ version, actor, reason }: DecisionVariables) =>
			deprecateStrategyVersion(strategyId, version, { actor, reason }),
		onSuccess: invalidateGovernedScopes,
	});
	const reactivate = useMutation({
		mutationFn: (variables: ReactivateVariables) =>
			reactivateStrategyVersion(strategyId, variables.version, {
				actor: variables.actor,
				reason: variables.reason,
				confirmation: variables.confirmation,
				impact_summary: variables.impactSummary,
				expected_pointer_revision: variables.expectedPointerRevision,
			}),
		onSuccess: invalidateGovernedScopes,
	});

	return { submitReview, approve, reject, deprecate, reactivate };
}
