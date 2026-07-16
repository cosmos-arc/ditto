import type {
	GetRiskBreachesResponse,
	GetRiskDrawdownResponse,
	GetRiskExposureResponse,
	GetRiskVarResponse,
} from "@/types";

export const mockRiskVar: GetRiskVarResponse = {
	series: [
		{ date: "2026-03-20", var95: -1.8, var99: -2.9 },
		{ date: "2026-03-21", var95: -1.6, var99: -2.7 },
		{ date: "2026-03-24", var95: -2.0, var99: -3.2 },
		{ date: "2026-03-25", var95: -2.1, var99: -3.4 },
		{ date: "2026-03-26", var95: -1.9, var99: -3.1 },
		{ date: "2026-03-27", var95: -1.7, var99: -2.8 },
		{ date: "2026-03-28", var95: -2.3, var99: -3.6 },
		{ date: "2026-03-31", var95: -2.0, var99: -3.2 },
		{ date: "2026-04-01", var95: -1.8, var99: -2.9 },
		{ date: "2026-04-02", var95: -2.2, var99: -3.5 },
		{ date: "2026-04-03", var95: -2.4, var99: -3.8 },
		{ date: "2026-04-04", var95: -2.1, var99: -3.3 },
		{ date: "2026-04-07", var95: -1.9, var99: -3.0 },
		{ date: "2026-04-08", var95: -2.0, var99: -3.1 },
		{ date: "2026-04-09", var95: -2.3, var99: -3.7 },
	] as const,
} as const;

export const mockRiskDrawdown: GetRiskDrawdownResponse = {
	series: [
		{ date: "2026-03-20", drawdown: -0.5, maxDD: -2.1 },
		{ date: "2026-03-21", drawdown: -0.2, maxDD: -2.1 },
		{ date: "2026-03-24", drawdown: -1.8, maxDD: -2.1 },
		{ date: "2026-03-25", drawdown: -2.1, maxDD: -2.1 },
		{ date: "2026-03-26", drawdown: -1.5, maxDD: -2.1 },
		{ date: "2026-03-27", drawdown: -0.8, maxDD: -2.1 },
		{ date: "2026-03-28", drawdown: -1.2, maxDD: -2.1 },
		{ date: "2026-03-31", drawdown: -0.3, maxDD: -2.1 },
		{ date: "2026-04-01", drawdown: -0.1, maxDD: -2.1 },
		{ date: "2026-04-02", drawdown: -1.0, maxDD: -2.1 },
		{ date: "2026-04-03", drawdown: -2.8, maxDD: -2.8 },
		{ date: "2026-04-04", drawdown: -1.9, maxDD: -2.8 },
		{ date: "2026-04-07", drawdown: -1.2, maxDD: -2.8 },
		{ date: "2026-04-08", drawdown: -0.6, maxDD: -2.8 },
		{ date: "2026-04-09", drawdown: -0.9, maxDD: -2.8 },
	] as const,
} as const;

export const mockRiskExposure: GetRiskExposureResponse = {
	grossExposure: 185,
	netExposure: 62,
	bySector: [
		{ name: "金融", long: 38, short: 8, net: 30 },
		{ name: "消费", long: 32, short: 5, net: 27 },
		{ name: "新能源", long: 25, short: 12, net: 13 },
		{ name: "医药", long: 18, short: 10, net: 8 },
		{ name: "科技", long: 15, short: 6, net: 9 },
	] as const,
	byStyle: [
		{ name: "大盘价值", long: 55, short: 12, net: 43 },
		{ name: "中盘成长", long: 40, short: 18, net: 22 },
		{ name: "小盘动量", long: 20, short: 10, net: 10 },
	] as const,
	byFactor: [
		{ name: "Beta", long: 0.92, short: 0.35, net: 0.57 },
		{ name: "动量", long: 0.45, short: -0.12, net: 0.57 },
		{ name: "波动率", long: 0.78, short: 0.25, net: 0.53 },
	] as const,
} as const;

export const mockRiskBreaches: GetRiskBreachesResponse = {
	items: [
		{
			id: "rb-001",
			ruleName: "单日 VaR 超限",
			currentValue: -3.8,
			threshold: -3.5,
			deviation: 8.6,
			affectedPositions: ["000001.SZ", "300750.SZ"],
			status: "active",
		},
		{
			id: "rb-002",
			ruleName: "行业集中度超限",
			currentValue: 22.5,
			threshold: 20.0,
			deviation: 12.5,
			affectedPositions: ["600519.SH", "000858.SZ", "002304.SZ"],
			status: "acknowledged",
		},
	] as const,
	total: 2,
	page: 1,
	pageSize: 20,
} as const;
