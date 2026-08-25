import type { paths } from "@/types/generated/api";

type Assert<T extends true> = T;

export type RequiredLiveApiPath =
	| "/api/v1/trade/daily-decision/v3"
	| "/api/v1/agent/capabilities"
	| "/api/v1/agent/sessions"
	| "/api/v1/agent/runs"
	| "/api/v1/agent/runs/{run_id}"
	| "/api/v1/agent/runs/{run_id}/cancel"
	| "/api/v1/agent/runs/{run_id}/events"
	| "/api/v1/agent/approvals"
	| "/api/v1/agent/approvals/{approval_id}"
	| "/api/v1/agent/approvals/{approval_id}/decision"
	| "/api/v1/agent/campaigns"
	| "/api/v1/agent/campaigns/{campaign_id}"
	| "/api/v1/agent/campaigns/{campaign_id}/approve"
	| "/api/v1/agent/campaigns/{campaign_id}/cancel"
	| "/api/v1/agent/campaigns/{campaign_id}/events"
	| "/api/v1/agent/decision-opinions";

type MissingRequiredLiveApiPath = Exclude<RequiredLiveApiPath, keyof paths>;

export type GeneratedApiIncludesRequiredLivePaths = Assert<MissingRequiredLiveApiPath extends never ? true : false>;
