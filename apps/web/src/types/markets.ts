import type { FilterCondition, PaginatedRequest, PaginatedResponse, SparklinePoint } from "./common";

// === Request Types ===

export type GetMarketContextRequest = undefined;

export type GetScopeStripRequest = undefined;

export type GetMarketOverviewRequest = undefined;

export type GetCrossMatrixRequest = undefined;

export type GetMacroDriversRequest = undefined;

export type GetCapitalRotationRequest = undefined;

export type GetMarketCalendarRequest = PaginatedRequest;

export type RunScreenerRequest = {
	readonly filters?: readonly FilterCondition[];
	readonly universe?: string;
	readonly sortBy?: string;
	readonly limit?: number;
	readonly offset?: number;
};

export type GetScreenerPresetsRequest = undefined;

export type GetScreenerColumnsRequest = undefined;

export type CompareInstrumentsRequest = {
	readonly ids: readonly string[];
};

export type GetIntelligenceFlowRequest = undefined;

export type GetIntelligenceMacroRequest = undefined;

export type GetIntelligenceFundamentalsRequest = undefined;

export type GetIntelligenceNewsRequest = PaginatedRequest;

export type GetIntelligenceNetworkRequest = undefined;

export type GetIntelligenceDetailRequest = {
	readonly id: string;
};

// === Response Types ===

/** 市场上下文 */
export type MarketContextResponse = {
	readonly regime: string;
	readonly volatility: number;
	readonly usdStrength: number;
	readonly alertCount: number;
};

/** 市场解读 */
export type ScopeStripResponse = {
	readonly interpretation: string;
	readonly leadingSectors: readonly string[];
	readonly laggingSectors: readonly string[];
	readonly style: string;
	readonly events: readonly MarketCalendarEvent[];
};

/** 市场概览卡片 */
export type MarketOverviewCard = {
	readonly name: string;
	readonly indexCode: string;
	readonly price: number;
	readonly change: number;
	readonly changePercent: number;
	readonly breadth: number;
	readonly driver: string;
	readonly regimeTag: string;
	readonly sparkline?: readonly SparklinePoint[];
};

export type GetMarketOverviewResponse = {
	readonly cards: readonly MarketOverviewCard[];
};

/** 跨市场矩阵行 */
export type CrossMatrixRow = {
	readonly name: string;
	readonly metrics: {
		readonly D1: number;
		readonly W1: number;
		readonly M1: number;
		readonly vol: number;
		readonly breadth: number;
		readonly flow: number;
	};
};

export type GetCrossMatrixResponse = {
	readonly rows: readonly CrossMatrixRow[];
};

/** 宏观驱动指标 */
export type MacroDriver = {
	readonly name: string;
	readonly value: number;
	readonly change: number;
	readonly sparkline: readonly SparklinePoint[];
};

export type GetMacroDriversResponse = {
	readonly indicators: readonly MacroDriver[];
};

/** 板块资金轮动 */
export type CapitalRotationSector = {
	readonly name: string;
	readonly inflow: number;
	readonly outflow: number;
	readonly netFlow: number;
	readonly rankChange: number;
};

export type GetCapitalRotationResponse = {
	readonly sectors: readonly CapitalRotationSector[];
};

/** 事件重要性 */
export type EventImportance = "high" | "medium" | "low";

/** 日历事件 */
export type MarketCalendarEvent = {
	readonly date: string;
	readonly time?: string;
	readonly title: string;
	readonly importance: EventImportance;
	readonly country: string;
	readonly type: string;
};

export type GetMarketCalendarResponse = PaginatedResponse<MarketCalendarEvent>;

/** A 股概览 */
export type ASharesIndexSummary = {
	readonly index: string;
	readonly price: number;
	readonly change: number;
	readonly changePercent: number;
	readonly volume: number;
	readonly turnover: number;
};

export type ASharesSectorMover = {
	readonly sector: string;
	readonly change: number;
	readonly topStock: string;
	readonly topStockChange: number;
};

export type ASharesETFItem = {
	readonly name: string;
	readonly code: string;
	readonly price: number;
	readonly change: number;
	readonly volume: number;
};

export type ASharesNorthboundFlow = {
	readonly date: string;
	readonly netBuy: number;
	readonly totalBuy: number;
	readonly totalSell: number;
};

export type ASharesOverviewResponse = {
	readonly summary: readonly ASharesIndexSummary[];
	readonly topGainers: readonly ASharesIndexSummary[];
	readonly topLosers: readonly ASharesIndexSummary[];
	readonly sectors: readonly ASharesSectorMover[];
	readonly etfMatrix: readonly ASharesETFItem[];
	readonly northboundFlow: readonly ASharesNorthboundFlow[];
};

/** Screener 结果 */
export type ScreenerResult = {
	readonly code: string;
	readonly name: string;
	readonly industry: string;
	readonly market: string;
	readonly price: number;
	readonly change: number;
	readonly changePercent: number;
	readonly volume: number;
	readonly turnover: number;
	readonly pe: number;
	readonly pb: number;
	readonly marketCap: number;
};

export type RunScreenerResponse = {
	readonly results: readonly ScreenerResult[];
	readonly total: number;
	readonly facets: Readonly<Record<string, number>>;
};

/** Screener 预设 */
export type ScreenerPreset = {
	readonly id: string;
	readonly name: string;
	readonly filters: readonly FilterCondition[];
	readonly builtin: boolean;
};

export type GetScreenerPresetsResponse = {
	readonly presets: readonly ScreenerPreset[];
};

/** Screener 列定义 */
export type ScreenerColumn = {
	readonly key: string;
	readonly label: string;
	readonly group: string;
	readonly sortable: boolean;
	readonly defaultVisible: boolean;
};

export type GetScreenerColumnsResponse = {
	readonly columns: readonly ScreenerColumn[];
};

/** 对比标的概览 */
export type CompareInstrumentOverview = {
	readonly id: string;
	readonly name: string;
	readonly code: string;
	readonly price: number;
	readonly change: number;
};

/** 对比标的技术面 */
export type CompareTechnical = {
	readonly rsi: number;
	readonly macd: number;
	readonly ma20: number;
	readonly ma60: number;
	readonly support: number;
	readonly resistance: number;
};

/** 对比标的基本面 */
export type CompareFundamental = {
	readonly pe: number;
	readonly pb: number;
	readonly roe: number;
	readonly debtRatio: number;
	readonly revenueGrowth: number;
	readonly profitGrowth: number;
};

/** 对比标的风控 */
export type CompareRisk = {
	readonly beta: number;
	readonly volatility: number;
	readonly maxDD: number;
	readonly sharpe: number;
};

/** 对比标的 */
export type CompareInstrument = {
	readonly id: string;
	readonly overview: CompareInstrumentOverview;
	readonly technical: CompareTechnical;
	readonly fundamental: CompareFundamental;
	readonly risk: CompareRisk;
};

export type CompareInstrumentsResponse = {
	readonly instruments: readonly CompareInstrument[];
};

/** 资金流向 */
export type NetFlowItem = {
	readonly date: string;
	readonly northbound: number;
	readonly southbound: number;
	readonly total: number;
};

export type SectorRanking = {
	readonly sector: string;
	readonly netFlow: number;
	readonly change: number;
	readonly rankChange: number;
};

export type LargeOrder = {
	readonly time: string;
	readonly code: string;
	readonly name: string;
	readonly side: string;
	readonly volume: number;
	readonly amount: number;
};

export type NorthboundFlow = {
	readonly date: string;
	readonly 沪股通: number;
	readonly 深股通: number;
	readonly total: number;
};

export type GetIntelligenceFlowResponse = {
	readonly netFlows: readonly NetFlowItem[];
	readonly sectorRankings: readonly SectorRanking[];
	readonly largeOrders: readonly LargeOrder[];
	readonly northbound: readonly NorthboundFlow[];
};

/** 宏观情报 */
export type MacroCalendar = {
	readonly date: string;
	readonly time: string;
	readonly country: string;
	readonly event: string;
	readonly actual?: number;
	readonly forecast: number;
	readonly previous: number;
	readonly importance: EventImportance;
};

export type MacroIndicator = {
	readonly name: string;
	readonly value: number;
	readonly change: number;
	readonly unit: string;
};

export type GetIntelligenceMacroResponse = {
	readonly calendar: readonly MacroCalendar[];
	readonly indicators: readonly MacroIndicator[];
	readonly yieldSpread: number;
	readonly fx: {
		readonly usdCny: number;
		readonly eurUsd: number;
	};
};

/** 基本面情报 */
export type EarningsCalendarItem = {
	readonly date: string;
	readonly code: string;
	readonly name: string;
	readonly epsActual?: number;
	readonly epsEstimate: number;
	readonly surprise?: number;
};

export type RatingChange = {
	readonly date: string;
	readonly code: string;
	readonly name: string;
	readonly org: string;
	readonly action: string;
	readonly rating: string;
};

export type EarningsEstimate = {
	readonly code: string;
	readonly name: string;
	readonly epsFY1: number;
	readonly epsFY2: number;
	readonly revision: number;
};

export type GetIntelligenceFundamentalsResponse = {
	readonly earningsCalendar: readonly EarningsCalendarItem[];
	readonly ratingChanges: readonly RatingChange[];
	readonly earningsEstimates: readonly EarningsEstimate[];
};

/** 新闻情报 */
export type IntelligenceNews = {
	readonly id: string;
	readonly title: string;
	readonly summary: string;
	readonly sentiment: "positive" | "negative" | "neutral";
	readonly source: string;
	readonly time: string;
};

export type GetIntelligenceNewsResponse = PaginatedResponse<IntelligenceNews>;

/** 关联网络 */
export type GetIntelligenceNetworkResponse = {
	readonly correlationMatrix: Readonly<Record<string, readonly number[]>>;
	readonly sectorLinkage: readonly {
		readonly sectorA: string;
		readonly sectorB: string;
		readonly correlation: number;
	}[];
	readonly supplyChain: readonly {
		readonly upstream: readonly string[];
		readonly downstream: readonly string[];
	}[];
};

/** 情报详情 */
export type IntelligenceDetail = {
	readonly id: string;
	readonly title: string;
	readonly content: string;
	readonly sources: readonly string[];
	readonly relatedIds: readonly string[];
	readonly createdAt: string;
	readonly updatedAt: string;
};

export type GetIntelligenceDetailResponse = IntelligenceDetail;
