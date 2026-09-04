import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
	type AgentStreamState,
	agentQueryKeys,
	approveAgentCampaign,
	cancelAgentCampaign,
	cancelAgentRun,
	createAgentCampaign,
	createAgentRun,
	createAgentSession,
	createRecoverableAgentEventStream,
	decideAgentApproval,
	executeAgentRun,
	fetchAgentCapability,
	fetchDecisionOpinion,
	getAgentApproval,
	getAgentCampaign,
	getAgentRun,
	listAgentApprovals,
	listAgentCampaigns,
	listAgentRuns,
	listAgentSessions,
	validateAgentCampaignStep,
} from "../api";
import type {
	AgentApprovalFilters,
	AgentCampaignFilters,
	AgentCampaignManifestInput,
	AgentCampaignValidationInput,
	AgentDecisionOpinionIdentity,
	AgentRunFilters,
	AgentRunView,
	CreateAgentRunInput,
} from "../types";

const STALE_TIME_MS = 15_000;

export function useAgentCapability() {
	return useQuery({
		queryKey: agentQueryKeys.capability(),
		queryFn: fetchAgentCapability,
		retry: false,
		staleTime: 30_000,
	});
}

export function useAgentSessions(offset = 0) {
	return useQuery({
		queryKey: agentQueryKeys.sessions(offset),
		queryFn: () => listAgentSessions(offset),
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentRuns(filters: AgentRunFilters, enabled = true) {
	return useQuery({
		queryKey: agentQueryKeys.runs(filters),
		queryFn: () => listAgentRuns(filters),
		enabled,
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentRun(runId: string) {
	return useQuery({
		queryKey: agentQueryKeys.run(runId),
		queryFn: () => getAgentRun(runId),
		enabled: runId.length > 0,
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentApprovals(filters: AgentApprovalFilters) {
	return useQuery({
		queryKey: agentQueryKeys.approvals(filters),
		queryFn: () => listAgentApprovals(filters),
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentApproval(approvalId: string) {
	return useQuery({
		queryKey: agentQueryKeys.approval(approvalId),
		queryFn: () => getAgentApproval(approvalId),
		enabled: approvalId.length > 0,
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentCampaigns(filters: AgentCampaignFilters) {
	return useQuery({
		queryKey: agentQueryKeys.campaigns(filters),
		queryFn: () => listAgentCampaigns(filters),
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useAgentCampaign(campaignId: string) {
	return useQuery({
		queryKey: agentQueryKeys.campaign(campaignId),
		queryFn: () => getAgentCampaign(campaignId),
		enabled: campaignId.length > 0,
		placeholderData: keepPreviousData,
		staleTime: STALE_TIME_MS,
	});
}

export function useCreateAgentRun() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (
			command: CreateAgentRunInput & {
				readonly executeImmediately?: boolean;
				readonly retentionClass: "ephemeral" | "standard" | "audit";
			},
		) => {
			let sessionId = command.sessionId;
			if (!sessionId) {
				const session = await createAgentSession(command.retentionClass, `${command.idempotencyKey}:session`);
				sessionId = session.sessionId;
			}
			const created = await createAgentRun({ ...command, sessionId });
			return command.executeImmediately ? executeAgentRun(created) : created;
		},
		onSuccess: (run) => {
			void queryClient.invalidateQueries({ queryKey: agentQueryKeys.all });
			queryClient.setQueryData(agentQueryKeys.run(run.runId), run);
		},
	});
}

export function useExecuteAgentRun() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (run: Pick<AgentRunView, "runId" | "revision">) => executeAgentRun(run),
		onSuccess: (run) => {
			queryClient.setQueryData(agentQueryKeys.run(run.runId), run);
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "runs"] });
		},
	});
}

export function useCancelAgentRun() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (run: Pick<AgentRunView, "runId" | "revision">) => cancelAgentRun(run),
		onSuccess: (run) => {
			queryClient.setQueryData(agentQueryKeys.run(run.runId), run);
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "runs"] });
		},
	});
}

export function useDecideAgentApproval() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: decideAgentApproval,
		onSuccess: (_result, command) => {
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "approvals"] });
			void queryClient.invalidateQueries({ queryKey: agentQueryKeys.approval(command.approvalId) });
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "runs"] });
		},
	});
}

export function useCreateAgentCampaign() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (command: { readonly manifest: AgentCampaignManifestInput; readonly idempotencyKey: string }) =>
			createAgentCampaign(command.manifest, command.idempotencyKey),
		onSuccess: (campaign) => {
			queryClient.setQueryData(agentQueryKeys.campaign(campaign.campaignId), campaign);
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "campaigns"] });
		},
	});
}

export function useValidateAgentCampaign() {
	return useMutation({
		mutationFn: (input: AgentCampaignValidationInput) => validateAgentCampaignStep(input),
	});
}

export function useApproveAgentCampaign() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: approveAgentCampaign,
		onSuccess: (campaign) => {
			queryClient.setQueryData(agentQueryKeys.campaign(campaign.campaignId), campaign);
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "campaigns"] });
		},
	});
}

export function useCancelAgentCampaign() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: cancelAgentCampaign,
		onSuccess: (campaign) => {
			queryClient.setQueryData(agentQueryKeys.campaign(campaign.campaignId), campaign);
			void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "campaigns"] });
		},
	});
}

export function useAgentEventNotifications(
	kind: "runs" | "campaigns",
	identity: string,
	cursor: number,
	enabled: boolean,
): AgentStreamState {
	const queryClient = useQueryClient();
	const [state, setState] = useState<AgentStreamState>("stopped");
	useEffect(() => {
		if (!enabled || !identity) {
			setState("stopped");
			return;
		}
		const stream = createRecoverableAgentEventStream({
			path: `/v1/agent/${kind}/${encodeURIComponent(identity)}/events`,
			initialCursor: cursor,
			visibilityTarget: document,
			onState: setState,
			onEvent: () => {
				void queryClient.invalidateQueries({
					queryKey: kind === "runs" ? agentQueryKeys.run(identity) : agentQueryKeys.campaign(identity),
				});
				void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, kind] });
				if (kind === "runs") {
					void queryClient.invalidateQueries({ queryKey: [...agentQueryKeys.all, "approvals"] });
				}
			},
		});
		stream.start();
		return () => stream.stop();
	}, [cursor, enabled, identity, kind, queryClient]);
	return state;
}

export function useDecisionOpinion(identity: AgentDecisionOpinionIdentity | null) {
	return useQuery({
		queryKey: agentQueryKeys.opinion(
			identity ?? {
				strategyId: "",
				strategyVersion: "",
				tradeDate: "",
				accountId: "",
				sleeveId: "",
				v3ArtifactId: "",
				decisionTime: "",
				knowledgeCutoff: "",
				publicationCutoff: "",
				sourceSnapshotId: "",
			},
		),
		queryFn: () => fetchDecisionOpinion(identity as AgentDecisionOpinionIdentity),
		enabled: identity !== null,
		retry: false,
		staleTime: 30_000,
	});
}
