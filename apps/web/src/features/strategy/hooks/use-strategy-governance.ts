import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { ApiError } from "@/api";
import { strategyKeys } from "../api/query-keys";
import {
	approveStrategyReview,
	deprecateStrategyVersion,
	publishStrategyVersion,
	reactivateStrategyVersion,
	rejectStrategyReview,
	submitStrategyReview,
} from "../api/strategy-lifecycle";

type EvidenceContext = { readonly experimentId?: string | null | undefined };

export type DecisionVariables = EvidenceContext & {
	readonly version: number;
	readonly actor: string;
	readonly reason: string;
};

export type SubmitVariables = DecisionVariables & { readonly bundleHash: string };

export type ReactivateVariables = EvidenceContext & {
	readonly version: number;
	readonly actor: string;
	readonly reason: string;
	readonly confirmation: string;
	readonly impactSummary: string;
	readonly expectedPointerRevision: number;
};

export type PublishVariables = EvidenceContext & {
	readonly version: number;
	readonly bundleHash: string;
	readonly actor: string;
	readonly reason: string;
};

function createIdempotencyKey(): string {
	return `strategy-governance-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function identity(action: string, variables: object): string {
	return `${action}:${JSON.stringify(variables)}`;
}

export function useStrategyGovernance(strategyId: string) {
	const queryClient = useQueryClient();
	const attempts = useRef(new Map<string, string>());

	function commandKey(action: string, variables: object): string {
		const id = identity(action, variables);
		const existing = attempts.current.get(id);
		if (existing) return existing;
		const key = createIdempotencyKey();
		attempts.current.set(id, key);
		return key;
	}

	function release(action: string, variables: object): void {
		attempts.current.delete(identity(action, variables));
	}

	async function recoverActivePointerAfterConflict(error: Error): Promise<void> {
		if (!(error instanceof ApiError) || error.status !== 409) return;
		const queryKey = strategyKeys.active(strategyId);
		await queryClient.invalidateQueries({ queryKey, refetchType: "none" });
		await queryClient.refetchQueries({ queryKey });
	}

	function invalidateGovernedScopes(experimentId?: string | null): void {
		void queryClient.invalidateQueries({ queryKey: strategyKeys.versions(strategyId) });
		void queryClient.invalidateQueries({ queryKey: strategyKeys.active(strategyId) });
		void queryClient.invalidateQueries({ queryKey: strategyKeys.events(strategyId) });
		void queryClient.invalidateQueries({ queryKey: ["research", "reviews", "list"] });
		if (!experimentId) return;
		void queryClient.invalidateQueries({ queryKey: ["research", "reviews", "packet", experimentId] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", "list"] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", "detail", experimentId] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", experimentId, "candidates"] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", experimentId, "gates"] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", experimentId, "comparison"] });
		void queryClient.invalidateQueries({ queryKey: ["research", "experiments", experimentId, "artifacts"] });
		void queryClient.invalidateQueries({
			queryKey: ["research", "experiments", experimentId, "selection-evidence"],
		});
		void queryClient.invalidateQueries({
			queryKey: ["research", "experiments", experimentId, "candidate-evidence"],
		});
	}

	const submitReview = useMutation({
		mutationFn: (variables: SubmitVariables) =>
			submitStrategyReview(
				strategyId,
				variables.version,
				{ actor: variables.actor, reason: variables.reason, bundle_hash: variables.bundleHash },
				commandKey("submit", variables),
			),
		onSuccess: (_data, variables) => {
			release("submit", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
	});
	const approve = useMutation({
		mutationFn: (variables: DecisionVariables) =>
			approveStrategyReview(
				strategyId,
				variables.version,
				{ actor: variables.actor, reason: variables.reason },
				commandKey("approve", variables),
			),
		onSuccess: (_data, variables) => {
			release("approve", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
	});
	const reject = useMutation({
		mutationFn: (variables: DecisionVariables) =>
			rejectStrategyReview(
				strategyId,
				variables.version,
				{ actor: variables.actor, reason: variables.reason },
				commandKey("reject", variables),
			),
		onSuccess: (_data, variables) => {
			release("reject", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
	});
	const deprecate = useMutation({
		mutationFn: (variables: DecisionVariables) =>
			deprecateStrategyVersion(
				strategyId,
				variables.version,
				{ actor: variables.actor, reason: variables.reason },
				commandKey("deprecate", variables),
			),
		onSuccess: (_data, variables) => {
			release("deprecate", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
	});
	const reactivate = useMutation({
		mutationFn: (variables: ReactivateVariables) =>
			reactivateStrategyVersion(
				strategyId,
				variables.version,
				{
					actor: variables.actor,
					reason: variables.reason,
					confirmation: variables.confirmation,
					impact_summary: variables.impactSummary,
					expected_pointer_revision: variables.expectedPointerRevision,
				},
				commandKey("reactivate", variables),
			),
		onSuccess: (_data, variables) => {
			release("reactivate", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
		onError: recoverActivePointerAfterConflict,
	});
	const publish = useMutation({
		mutationFn: (variables: PublishVariables) =>
			publishStrategyVersion(
				strategyId,
				variables.version,
				{ bundle_hash: variables.bundleHash, actor: variables.actor, reason: variables.reason },
				commandKey("publish", variables),
			),
		onSuccess: (_data, variables) => {
			release("publish", variables);
			invalidateGovernedScopes(variables.experimentId);
		},
	});

	return { submitReview, approve, reject, deprecate, reactivate, publish };
}
