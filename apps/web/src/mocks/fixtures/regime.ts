import type {
	GetRegimeCurrentResponse,
	GetRegimeDriversResponse,
	GetRegimeHistoryResponse,
	GetRegimeStrategyImpactResponse,
} from "@/types";

export const mockRegimeCurrent: GetRegimeCurrentResponse = {
	state: "risk_on",
	confidence: 0.78,
	duration: 15,
	keyIndicators: [
		{
			name: "波动率",
			value: 15.2,
			normal: true,
			description: "市场波动率处于正常偏低水平，有利于趋势策略",
		},
		{
			name: "动量",
			value: 0.65,
			normal: true,
			description: "市场动量指标偏强，多数板块上行趋势延续",
		},
		{
			name: "流动性",
			value: 82.5,
			normal: true,
			description: "市场流动性充裕，成交额维持在万亿以上",
		},
		{
			name: "市场宽度",
			value: 68.3,
			normal: true,
			description: "上涨个股占比近七成，赚钱效应良好",
		},
	],
} as const;

export const mockRegimeDrivers: GetRegimeDriversResponse = {
	drivers: [
		{
			name: "北向资金",
			value: 45.8,
			trend: "up",
			impact: "positive",
		},
		{
			name: "信用利差",
			value: 85.3,
			trend: "down",
			impact: "positive",
		},
		{
			name: "PMI",
			value: 50.8,
			trend: "up",
			impact: "positive",
		},
		{
			name: "VIX",
			value: 15.6,
			trend: "flat",
			impact: "neutral",
		},
		{
			name: "美元指数",
			value: 104.2,
			trend: "down",
			impact: "positive",
		},
	],
} as const;

export const mockRegimeHistory: GetRegimeHistoryResponse = {
	items: [
		{
			date: "2026-03-25",
			fromState: "volatile",
			toState: "risk_on",
			trigger: "北向资金大幅净流入 + PMI 超预期回升",
			confidence: 0.78,
		},
		{
			date: "2026-03-10",
			fromState: "risk_on",
			toState: "volatile",
			trigger: "美联储鹰派言论 + 美元指数急升",
			confidence: 0.72,
		},
		{
			date: "2026-02-20",
			fromState: "transition",
			toState: "risk_on",
			trigger: "两会政策利好集中释放 + 流动性宽松",
			confidence: 0.82,
		},
		{
			date: "2026-02-05",
			fromState: "risk_off",
			toState: "transition",
			trigger: "央行降准释放流动性 + 外资止减仓",
			confidence: 0.65,
		},
		{
			date: "2026-01-20",
			fromState: "risk_on",
			toState: "risk_off",
			trigger: "地缘冲突升级 + 全球风险资产抛售",
			confidence: 0.88,
		},
	],
	total: 5,
	page: 1,
	pageSize: 20,
} as const;

export const mockRegimeStrategyImpact: GetRegimeStrategyImpactResponse = {
	strategies: [
		{
			id: "strat-001",
			name: "动量突破 v3",
			performance: 12.5,
			adjustmentSuggestion: "当前 regime 适配度高，建议维持标准仓位，可适当增加动量因子权重",
		},
		{
			id: "strat-002",
			name: "多因子均衡 v2",
			performance: 8.3,
			adjustmentSuggestion: "建议降低价值因子权重，增加成长因子暴露以匹配 risk_on 环境",
		},
		{
			id: "strat-003",
			name: "市场中性对冲",
			performance: -1.2,
			adjustmentSuggestion: "risk_on 环境下 alpha 收窄，建议降低对冲比例或暂停该策略",
		},
	],
} as const;
