import type { SparklinePoint } from "./common";

// === Request Types ===

export type GetInstrumentRequest = {
	readonly id: string;
};

export type GetInstrumentChartRequest = {
	readonly id: string;
	readonly period: string;
	readonly interval: string;
};

export type GetInstrumentFlowRequest = {
	readonly id: string;
};

export type GetInstrumentFundamentalsRequest = {
	readonly id: string;
};

export type GetInstrumentCorporateActionsRequest = {
	readonly id: string;
};

export type GetInstrumentNewsRequest = {
	readonly id: string;
};

export type GetInstrumentNetworkRequest = {
	readonly id: string;
};

export type GetInstrumentAnnouncementsRequest = {
	readonly id: string;
};

// === Response Types ===

/** 标的状态 */
export type InstrumentStatus = "active" | "suspended" | "delisted" | "halted";

/** 标的详情 */
export type InstrumentDetail = {
	readonly id: string;
	readonly name: string;
	readonly code: string;
	readonly price: number;
	readonly change: number;
	readonly changePercent: number;
	readonly marketCap: number;
	readonly pe: number;
	readonly pb: number;
	readonly industry: string;
	readonly market: string;
	readonly tags: readonly string[];
	readonly status: InstrumentStatus;
};

export type GetInstrumentResponse = InstrumentDetail;

/** K 线数据 */
export type ChartBar = {
	readonly time: string;
	readonly open: number;
	readonly high: number;
	readonly low: number;
	readonly close: number;
	readonly volume: number;
};

export type ChartIndicators = {
	readonly ma5?: readonly (number | null)[];
	readonly ma20?: readonly (number | null)[];
	readonly ma60?: readonly (number | null)[];
	readonly volume?: readonly number[];
};

export type GetInstrumentChartResponse = {
	readonly bars: readonly ChartBar[];
	readonly indicators?: ChartIndicators;
};

/** 资金流向 */
export type FlowItem = {
	readonly date: string;
	readonly mainInflow: number;
	readonly mainOutflow: number;
	readonly retailInflow: number;
	readonly retailOutflow: number;
};

export type ChipDistribution = {
	readonly range: string;
	readonly ratio: number;
	readonly change: number;
};

export type GetInstrumentFlowResponse = {
	readonly institutional: readonly FlowItem[];
	readonly retail: readonly FlowItem[];
	readonly northbound: readonly FlowItem[];
	readonly chipDistribution: readonly ChipDistribution[];
};

/** 财务报表 */
export type FinancialStatement = {
	readonly period: string;
	readonly revenue: number;
	readonly netProfit: number;
	readonly grossMargin: number;
	readonly netMargin: number;
};

export type BalanceSheet = {
	readonly totalAssets: number;
	readonly totalLiabilities: number;
	readonly netAssets: number;
	readonly cash: number;
	readonly debt: number;
};

export type CashflowStatement = {
	readonly operatingCF: number;
	readonly investingCF: number;
	readonly financingCF: number;
	readonly freeCF: number;
};

export type FinancialRatio = {
	readonly name: string;
	readonly value: number;
	readonly description: string;
};

export type DupontAnalysis = {
	readonly roe: number;
	readonly netMargin: number;
	readonly assetTurnover: number;
	readonly equityMultiplier: number;
};

export type PeerComparison = {
	readonly code: string;
	readonly name: string;
	readonly pe: number;
	readonly pb: number;
	readonly roe: number;
};

export type GetInstrumentFundamentalsResponse = {
	readonly income: readonly FinancialStatement[];
	readonly balance: readonly BalanceSheet[];
	readonly cashflow: readonly CashflowStatement[];
	readonly ratios: readonly FinancialRatio[];
	readonly dupontAnalysis: DupontAnalysis;
	readonly peers: readonly PeerComparison[];
};

/** 公司行动 */
export type Dividend = {
	readonly exDate: string;
	readonly recordDate: string;
	readonly payDate: string;
	readonly dividendPerShare: number;
	readonly dividendYield: number;
};

export type LockupExpiry = {
	readonly date: string;
	readonly shares: number;
	readonly percentage: number;
};

export type ShareholderChange = {
	readonly shareholder: string;
	readonly shares: number;
	readonly percentage: number;
	readonly change: number;
	readonly date: string;
};

export type InstitutionalHolding = {
	readonly institution: string;
	readonly shares: number;
	readonly percentage: number;
	readonly change: number;
	readonly reportDate: string;
};

export type GetInstrumentCorporateActionsResponse = {
	readonly dividends: readonly Dividend[];
	readonly lockupExpiry: readonly LockupExpiry[];
	readonly shareholderChanges: readonly ShareholderChange[];
	readonly institutionalHoldings: readonly InstitutionalHolding[];
};

/** 标的新闻 */
export type InstrumentNews = {
	readonly id: string;
	readonly title: string;
	readonly summary: string;
	readonly sentiment: "positive" | "negative" | "neutral";
	readonly time: string;
	readonly source: string;
};

export type GetInstrumentNewsResponse = {
	readonly news: readonly InstrumentNews[];
};

/** 关联标的 */
export type RelationType =
	| "same_industry"
	| "supply_chain"
	| "concept"
	| "holding";

export type RelatedInstrument = {
	readonly id: string;
	readonly name: string;
	readonly code: string;
	readonly relationType: RelationType;
	readonly strength: number;
};

export type GetInstrumentNetworkResponse = {
	readonly relatedInstruments: readonly RelatedInstrument[];
};

/** 公告 */
export type Announcement = {
	readonly id: string;
	readonly title: string;
	readonly type: string;
	readonly importance: "high" | "medium" | "low";
	readonly date: string;
	readonly summary?: string;
};

export type GetInstrumentAnnouncementsResponse = {
	readonly announcements: readonly Announcement[];
};
