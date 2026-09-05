import type {
	GetIntelligenceFlowResponse,
	GetIntelligenceFundamentalsResponse,
	GetIntelligenceMacroResponse,
} from "@/types";

export const mockIntelligenceFlow: GetIntelligenceFlowResponse = {
	netFlows: [
		{ date: "2026-04-08", northbound: 45.8, southbound: 22.3, total: 23.5 },
		{ date: "2026-04-07", northbound: 38.2, southbound: 18.5, total: 19.7 },
		{ date: "2026-04-04", northbound: -12.3, southbound: 25.1, total: -37.4 },
		{ date: "2026-04-03", northbound: 52.1, southbound: 15.8, total: 36.3 },
		{ date: "2026-04-02", northbound: 28.6, southbound: 20.2, total: 8.4 },
	],
	sectorRankings: [
		{ sector: "科技", netFlow: 23.5, change: 2.8, rankChange: 1 },
		{ sector: "新能源", netFlow: 15.2, change: 1.5, rankChange: 2 },
		{ sector: "消费", netFlow: 12.8, change: -0.3, rankChange: -1 },
		{ sector: "医药", netFlow: -5.4, change: -2.1, rankChange: -2 },
		{ sector: "银行", netFlow: -8.6, change: -1.5, rankChange: 0 },
	],
	largeOrders: [
		{ time: "14:32:15", code: "600519.SH", name: "贵州茅台", side: "buy", volume: 5200, amount: 8764.0 },
		{ time: "13:45:08", code: "300750.SZ", name: "宁德时代", side: "sell", volume: 18000, amount: 3578.4 },
		{ time: "10:22:33", code: "002594.SZ", name: "比亚迪", side: "buy", volume: 12500, amount: 3317.5 },
	],
	northbound: [
		{ date: "2026-04-08", 沪股通: 28.5, 深股通: 17.3, total: 45.8 },
		{ date: "2026-04-07", 沪股通: 22.1, 深股通: 16.1, total: 38.2 },
		{ date: "2026-04-04", 沪股通: -8.2, 深股通: -4.1, total: -12.3 },
		{ date: "2026-04-03", 沪股通: 32.5, 深股通: 19.6, total: 52.1 },
		{ date: "2026-04-02", 沪股通: 18.3, 深股通: 10.3, total: 28.6 },
	],
} as const;

export const mockIntelligenceMacro: GetIntelligenceMacroResponse = {
	calendar: [
		{
			date: "2026-04-10",
			time: "09:30",
			country: "中国",
			event: "CPI 同比",
			forecast: 0.3,
			previous: 0.2,
			importance: "high",
		},
		{
			date: "2026-04-10",
			time: "10:00",
			country: "中国",
			event: "PPI 同比",
			forecast: -2.1,
			previous: -2.3,
			importance: "medium",
		},
		{
			date: "2026-04-11",
			time: "20:30",
			country: "美国",
			event: "CPI 同比",
			forecast: 3.2,
			previous: 3.1,
			importance: "high",
		},
		{
			date: "2026-04-11",
			time: "20:30",
			country: "美国",
			event: "核心 CPI 同比",
			forecast: 3.5,
			previous: 3.4,
			importance: "high",
		},
		{
			date: "2026-04-12",
			time: "09:30",
			country: "中国",
			event: "社会融资规模",
			forecast: 25000,
			previous: 23600,
			importance: "medium",
		},
	],
	indicators: [
		{ name: "PMI 制造业", value: 50.8, change: 0.3, unit: "" },
		{ name: "PMI 非制造业", value: 52.5, change: 0.8, unit: "" },
		{ name: "M2 同比", value: 8.2, change: 0.1, unit: "%" },
		{ name: "社融存量同比", value: 9.5, change: -0.2, unit: "%" },
	],
	yieldSpread: -1.92,
	fx: {
		usdCny: 7.2456,
		eurUsd: 1.0832,
	},
} as const;

export const mockIntelligenceFundamentals: GetIntelligenceFundamentalsResponse = {
	earningsCalendar: [
		{
			date: "2026-04-10",
			code: "600519.SH",
			name: "贵州茅台",
			epsEstimate: 15.8,
		},
		{
			date: "2026-04-12",
			code: "300750.SZ",
			name: "宁德时代",
			epsEstimate: 3.2,
		},
		{
			date: "2026-04-15",
			code: "002594.SZ",
			name: "比亚迪",
			epsEstimate: 2.85,
		},
	],
	ratingChanges: [
		{ date: "2026-04-08", code: "601318.SH", name: "中国平安", org: "中金公司", action: "上调", rating: "跑赢行业" },
		{ date: "2026-04-07", code: "000333.SZ", name: "美的集团", org: "国泰君安", action: "维持", rating: "增持" },
	],
	earningsEstimates: [
		{ code: "600519.SH", name: "贵州茅台", epsFY1: 68.5, epsFY2: 75.2, revision: 2.3 },
		{ code: "300750.SZ", name: "宁德时代", epsFY1: 12.8, epsFY2: 15.5, revision: 5.1 },
		{ code: "002594.SZ", name: "比亚迪", epsFY1: 11.2, epsFY2: 13.8, revision: 3.5 },
	],
} as const;
