import type { GetFactorLibraryResponse, GetStrategyVersionsResponse, StrategyDetail } from "@/types";

// === 策略详情 ===

export const mockStrategyDetail: StrategyDetail = {
	id: "strat-001",
	name: "多因子动量策略 v3",
	version: 3,
	mode: "form",
	status: "completed",
	factors: ["动量因子", "波动率因子", "北向资金因子"],
	pipeline: {
		nodes: [
			{
				id: "node-1",
				name: "股票池过滤",
				type: "universe_filter",
				config: { universe: "沪深300", exclude_st: true, exclude_new: true },
			},
			{
				id: "node-2",
				name: "因子合成",
				type: "factor_combine",
				config: {
					method: "weighted_sum",
					normalize: true,
					factors: ["动量因子", "波动率因子", "北向资金因子"],
				},
			},
			{
				id: "node-3",
				name: "风控检查",
				type: "risk_check",
				config: {
					max_position_weight: 0.1,
					max_sector_exposure: 0.15,
					max_turnover: 0.3,
				},
			},
		],
		edges: [
			{ from: "node-1", to: "node-2" },
			{ from: "node-2", to: "node-3" },
		],
	},
	universe: "沪深300",
	weightConfig: {
		动量因子: 0.4,
		波动率因子: 0.3,
		北向资金因子: 0.3,
	},
	riskRules: [
		{
			name: "个股最大持仓权重",
			type: "position_limit",
			params: { max_weight: 10 },
			enabled: true,
		},
		{
			name: "行业最大暴露",
			type: "sector_exposure",
			params: { max_exposure: 15 },
			enabled: true,
		},
	],
	savedAt: "2026-04-08T15:00:00Z",
};

// === 策略版本 ===

export const mockStrategyVersions: GetStrategyVersionsResponse = {
	versions: [
		{
			version: 1,
			code: `def strategy(context):
    universe = context.get_universe("沪深300")
    scores = {}
    for stock in universe:
        momentum = context.get_factor(stock, "动量因子")
        scores[stock] = momentum
    return context.rank_and_select(scores, top_n=50)`,
			savedAt: "2026-04-01T10:00:00Z",
			changeNote: "初始版本：单因子动量策略",
		},
		{
			version: 2,
			code: `def strategy(context):
    universe = context.get_universe("沪深300")
    scores = {}
    for stock in universe:
        momentum = context.get_factor(stock, "动量因子")
        volatility = context.get_factor(stock, "波动率因子")
        scores[stock] = 0.6 * momentum - 0.4 * volatility
    return context.rank_and_select(scores, top_n=50)`,
			savedAt: "2026-04-05T14:30:00Z",
			changeNote: "新增波动率因子，调整权重配比",
		},
		{
			version: 3,
			code: `def strategy(context):
    universe = context.get_universe("沪深300")
    scores = {}
    for stock in universe:
        momentum = context.get_factor(stock, "动量因子")
        volatility = context.get_factor(stock, "波动率因子")
        northbound = context.get_factor(stock, "北向资金因子")
        scores[stock] = 0.4 * momentum - 0.3 * volatility + 0.3 * northbound
    return context.rank_and_select(scores, top_n=50)`,
			savedAt: "2026-04-08T15:00:00Z",
			changeNote: "新增北向资金因子，优化风控参数",
		},
	],
};

// === 因子库 ===

export const mockFactorLibrary: GetFactorLibraryResponse = {
	items: [
		{
			id: "lib-f-001",
			name: "动量因子",
			family: "技术面",
			description: "基于过去 N 日收益率排名的动量信号，捕捉价格趋势延续性",
			source: "内部计算",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
			],
		},
		{
			id: "lib-f-002",
			name: "价值因子",
			family: "基本面",
			description: "基于 PE、PB、PS 等估值指标的综合价值评分",
			source: "内部计算",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
				{ name: "中性化", params: { method: "industry", window: 60 } },
			],
		},
		{
			id: "lib-f-003",
			name: "波动率因子",
			family: "风险面",
			description: "基于历史收益率标准差和 GARCH 模型的波动率估计",
			source: "内部计算",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
			],
		},
		{
			id: "lib-f-004",
			name: "情绪因子",
			family: "另类",
			description: "基于新闻情感分析、搜索指数和社交媒体热度综合评分",
			source: "外部数据",
			preprocessorOptions: [
				{ name: "平滑", params: { method: "ewm", span: 5 } },
				{ name: "标准化", params: { method: "zscore" } },
			],
		},
		{
			id: "lib-f-005",
			name: "北向资金因子",
			family: "资金流",
			description: "基于沪深港通北向资金净流入和个股持仓变动的资金流信号",
			source: "交易所数据",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
				{ name: "平滑", params: { method: "ewm", span: 5 } },
			],
		},
		{
			id: "lib-f-006",
			name: "质量因子",
			family: "基本面",
			description: "基于 ROE、资产周转率、财务稳健性等指标的企业质量综合评分",
			source: "财务数据",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
				{ name: "中性化", params: { method: "industry", window: 60 } },
			],
		},
		{
			id: "lib-f-007",
			name: "规模因子",
			family: "基本面",
			description: "基于总市值和流通市值的规模效应因子",
			source: "行情数据",
			preprocessorOptions: [
				{ name: "取对数", params: { base: "ln" } },
				{ name: "标准化", params: { method: "zscore" } },
			],
		},
		{
			id: "lib-f-008",
			name: "行业动量因子",
			family: "技术面",
			description: "基于行业指数收益率排名的行业轮动信号",
			source: "内部计算",
			preprocessorOptions: [
				{ name: "去极值", params: { method: "mad", n_sigma: 3 } },
				{ name: "标准化", params: { method: "zscore" } },
			],
		},
	],
	total: 42,
	page: 1,
	pageSize: 20,
};
