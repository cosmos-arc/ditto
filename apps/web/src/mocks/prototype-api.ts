import { isMockRuntime } from "@/api";
import type {
	DecisionBannerResponse,
	FactorAnalysisResponse,
	FactorDetailResponse,
	GetDataHealthResponse,
	GetEquityResponse,
	GetFactorsResponse,
	GetHomeAgentFindingsResponse,
	GetHomeAlertsResponse,
	GetMarketIndicesResponse,
	GetMarketPulseMetricsResponse,
	GetOrderDetailResponse,
	GetOrdersRequest,
	GetOrdersResponse,
	GetOrdersSummaryResponse,
	GetPendingActionsResponse,
	GetPositionsResponse,
	GetRecentSignalsResponse,
	GetResearchRunsResponse,
	GetReviewQueueResponse,
	GetRiskBreachesRequest,
	GetRiskBreachesResponse,
	GetRiskDrawdownResponse,
	GetRiskExposureResponse,
	GetRiskVarResponse,
	GetSignalDetailResponse,
	GetSignalsQueueResponse,
	GetSignalsRequest,
	GetSignalsResponse,
	HomePulseResponse,
	PaginatedRequest,
	PortfolioSessionResponse,
	ResearchPulseResponse,
	RiskSummaryResponse,
} from "@/types";

function query(path: string, values?: Readonly<Record<string, string | number | undefined>>): string {
	const url = new URL(`/api${path}`, "http://localhost");
	for (const [key, value] of Object.entries(values ?? {})) {
		if (value !== undefined) url.searchParams.set(key, String(value));
	}
	return `${url.pathname}${url.search}`;
}

async function prototypeGet<Result>(path: string): Promise<Result> {
	if (!isMockRuntime()) throw new Error("prototype API is forbidden outside mock runtime");
	const response = await fetch(path, { headers: { Accept: "application/json" } });
	if (!response.ok) throw new Error(`prototype API failed with HTTP ${response.status}`);
	const payload: unknown = await response.json();
	if (typeof payload === "object" && payload !== null && "data" in payload) {
		return (payload as { readonly data: Result }).data;
	}
	return payload as Result;
}

export const getHomeAgentFindings = (): Promise<GetHomeAgentFindingsResponse> =>
	prototypeGet("/api/home/agent-findings");
export const getDataHealth = (): Promise<GetDataHealthResponse> => prototypeGet("/api/home/data-health");
export const getDecisionBanner = (): Promise<DecisionBannerResponse> => prototypeGet("/api/home/decision-banner");
export const getHomeAlerts = (): Promise<GetHomeAlertsResponse> => prototypeGet("/api/home/alerts");
export const getHomePulse = (): Promise<HomePulseResponse> => prototypeGet("/api/home/pulse");
export const getMarketIndices = (): Promise<GetMarketIndicesResponse> => prototypeGet("/api/market/indices");
export const getMarketPulseMetrics = (): Promise<GetMarketPulseMetricsResponse> =>
	prototypeGet("/api/home/pulse-metrics");
export const getPendingActions = (): Promise<GetPendingActionsResponse> => prototypeGet("/api/home/pending-actions");
export const getRecentSignals = (): Promise<GetRecentSignalsResponse> => prototypeGet("/api/home/signals/recent");

export const getEquity = (): Promise<GetEquityResponse> => prototypeGet("/api/trading/equity");
export const getOrderDetail = (id: string): Promise<GetOrderDetailResponse> =>
	prototypeGet(`/api/trading/orders/${encodeURIComponent(id)}`);
export const getOrdersSummary = (): Promise<GetOrdersSummaryResponse> => prototypeGet("/api/trading/orders/summary");
export const getOrders = (params?: GetOrdersRequest): Promise<GetOrdersResponse> =>
	prototypeGet(query("/trading/orders", params));
export const getPortfolioSession = (): Promise<PortfolioSessionResponse> => prototypeGet("/api/trading/session");
export const getPositions = (): Promise<GetPositionsResponse> => prototypeGet("/api/trading/positions");
export const getRiskBreaches = (params?: GetRiskBreachesRequest): Promise<GetRiskBreachesResponse> =>
	prototypeGet(query("/trading/risk/breaches", params));
export const getRiskDrawdown = (): Promise<GetRiskDrawdownResponse> => prototypeGet("/api/trading/risk/drawdown");
export const getRiskExposure = (): Promise<GetRiskExposureResponse> => prototypeGet("/api/trading/risk/exposure");
export const getRiskSummary = (): Promise<RiskSummaryResponse> => prototypeGet("/api/trading/risk/summary");
export const getRiskVar = (): Promise<GetRiskVarResponse> => prototypeGet("/api/trading/risk/var");
export const getSignalDetail = (id: string): Promise<GetSignalDetailResponse> =>
	prototypeGet(`/api/portfolio/review/${encodeURIComponent(id)}`);
export const getSignalsQueue = (): Promise<GetSignalsQueueResponse> => prototypeGet("/api/portfolio/review/queue");
export const getSignals = (params?: GetSignalsRequest): Promise<GetSignalsResponse> =>
	prototypeGet(query("/portfolio/review", params));

export const getResearchPulse = (): Promise<ResearchPulseResponse> => prototypeGet("/api/research/pulse");
export const getFactors = (params?: PaginatedRequest): Promise<GetFactorsResponse> =>
	prototypeGet(query("/factors", params));
export const getResearchRuns = (): Promise<GetResearchRunsResponse> => prototypeGet("/api/research/runs");
export const getReviewQueue = (): Promise<GetReviewQueueResponse> => prototypeGet("/api/research/review-queue");
export const getFactorDetail = (id: string): Promise<FactorDetailResponse> =>
	prototypeGet(`/api/factors/${encodeURIComponent(id)}`);
export const getFactorAnalysis = (id: string): Promise<FactorAnalysisResponse> =>
	prototypeGet(`/api/factors/${encodeURIComponent(id)}/analysis`);
