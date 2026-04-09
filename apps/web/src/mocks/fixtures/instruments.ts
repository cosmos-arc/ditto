import type {
	ChartBar,
	ChartIndicators,
	DupontAnalysis,
	FinancialRatio,
	FinancialStatement,
	BalanceSheet,
	CashflowStatement,
	GetInstrumentChartResponse,
	GetInstrumentFundamentalsResponse,
	InstrumentDetail,
	PeerComparison,
} from "@/types";

// === 标的详情 ===

export const mockInstrumentDetail: InstrumentDetail = {
	id: "600519.SH",
	name: "贵州茅台",
	code: "600519.SH",
	price: 1755.5,
	change: 12.3,
	changePercent: 0.71,
	marketCap: 2_206_000_000_000,
	pe: 33.5,
	pb: 11.2,
	industry: "白酒",
	market: "A股主板",
	tags: ["白酒龙头", "消费蓝筹"],
	status: "active",
};

// === K 线数据 ===

export const mockInstrumentBars: readonly ChartBar[] = [
	{ time: "2026-03-10", open: 1742.0, high: 1758.5, low: 1738.2, close: 1750.8, volume: 3_210_000 },
	{ time: "2026-03-11", open: 1751.2, high: 1762.3, low: 1748.5, close: 1758.6, volume: 2_850_000 },
	{ time: "2026-03-12", open: 1759.0, high: 1765.0, low: 1745.8, close: 1748.2, volume: 3_420_000 },
	{ time: "2026-03-13", open: 1747.5, high: 1755.3, low: 1740.1, close: 1743.7, volume: 3_680_000 },
	{ time: "2026-03-14", open: 1744.2, high: 1756.8, low: 1742.0, close: 1752.4, volume: 2_960_000 },
	{ time: "2026-03-17", open: 1753.0, high: 1761.5, low: 1749.3, close: 1758.9, volume: 3_150_000 },
	{ time: "2026-03-18", open: 1759.5, high: 1768.2, low: 1756.0, close: 1765.1, volume: 3_580_000 },
	{ time: "2026-03-19", open: 1764.8, high: 1769.3, low: 1752.5, close: 1755.3, volume: 4_120_000 },
	{ time: "2026-03-20", open: 1756.0, high: 1760.2, low: 1743.8, close: 1748.6, volume: 3_740_000 },
	{ time: "2026-03-21", open: 1747.2, high: 1755.0, low: 1740.5, close: 1742.8, volume: 3_320_000 },
	{ time: "2026-03-24", open: 1743.5, high: 1752.8, low: 1738.0, close: 1750.2, volume: 2_780_000 },
	{ time: "2026-03-25", open: 1751.0, high: 1763.5, low: 1749.2, close: 1760.8, volume: 3_450_000 },
	{ time: "2026-03-26", open: 1761.2, high: 1767.0, low: 1755.5, close: 1758.3, volume: 2_920_000 },
	{ time: "2026-03-27", open: 1757.8, high: 1765.5, low: 1748.0, close: 1753.1, volume: 3_660_000 },
	{ time: "2026-03-28", open: 1754.0, high: 1762.8, low: 1750.5, close: 1758.7, volume: 3_180_000 },
	{ time: "2026-03-31", open: 1759.2, high: 1770.5, low: 1755.0, close: 1766.4, volume: 4_050_000 },
	{ time: "2026-04-01", open: 1765.0, high: 1771.3, low: 1758.2, close: 1762.5, volume: 3_830_000 },
	{ time: "2026-04-02", open: 1763.8, high: 1769.0, low: 1752.3, close: 1755.0, volume: 3_510_000 },
	{ time: "2026-04-03", open: 1754.5, high: 1763.8, low: 1748.5, close: 1760.2, volume: 3_270_000 },
	{ time: "2026-04-04", open: 1761.0, high: 1770.0, low: 1757.5, close: 1755.5, volume: 3_890_000 },
] as const;

export const mockInstrumentIndicators: ChartIndicators = {
	ma5: [null, null, null, null, 1750.74, 1752.82, 1755.48, 1755.72, 1755.24, 1751.68, 1750.58, 1753.14, 1756.48, 1756.84, 1755.64, 1759.34, 1763.16, 1760.28, 1757.84],
	ma20: [null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, 1753.72, 1754.55, 1755.28, 1755.85],
};

export const mockInstrumentChart: GetInstrumentChartResponse = {
	bars: mockInstrumentBars,
	indicators: mockInstrumentIndicators,
};

// === 财务报表 ===

export const mockIncome: readonly FinancialStatement[] = [
	{ period: "2025Q3", revenue: 37_285_000_000, netProfit: 17_621_000_000, grossMargin: 0.915, netMargin: 0.473 },
	{ period: "2025Q2", revenue: 36_132_000_000, netProfit: 17_082_000_000, grossMargin: 0.912, netMargin: 0.473 },
	{ period: "2025Q1", revenue: 34_856_000_000, netProfit: 16_543_000_000, grossMargin: 0.918, netMargin: 0.475 },
	{ period: "2024Q4", revenue: 39_210_000_000, netProfit: 18_765_000_000, grossMargin: 0.921, netMargin: 0.479 },
] as const;

export const mockBalance: readonly BalanceSheet[] = [
	{ totalAssets: 258_430_000_000, totalLiabilities: 62_150_000_000, netAssets: 196_280_000_000, cash: 85_320_000_000, debt: 0 },
	{ totalAssets: 255_780_000_000, totalLiabilities: 61_520_000_000, netAssets: 194_260_000_000, cash: 83_150_000_000, debt: 0 },
	{ totalAssets: 252_610_000_000, totalLiabilities: 60_890_000_000, netAssets: 191_720_000_000, cash: 80_940_000_000, debt: 0 },
	{ totalAssets: 249_850_000_000, totalLiabilities: 60_230_000_000, netAssets: 189_620_000_000, cash: 78_560_000_000, debt: 0 },
] as const;

export const mockCashflow: readonly CashflowStatement[] = [
	{ operatingCF: 22_350_000_000, investingCF: -5_120_000_000, financingCF: -18_450_000_000, freeCF: 17_230_000_000 },
	{ operatingCF: 21_680_000_000, investingCF: -4_830_000_000, financingCF: -16_920_000_000, freeCF: 16_850_000_000 },
	{ operatingCF: 20_950_000_000, investingCF: -4_560_000_000, financingCF: -15_380_000_000, freeCF: 16_390_000_000 },
	{ operatingCF: 23_820_000_000, investingCF: -5_450_000_000, financingCF: -20_150_000_000, freeCF: 18_370_000_000 },
] as const;

// === 财务比率 ===

export const mockRatios: readonly FinancialRatio[] = [
	{ name: "ROE", value: 8.98, description: "净资产收益率（年化）" },
	{ name: "ROA", value: 6.82, description: "总资产收益率（年化）" },
	{ name: "毛利率", value: 91.5, description: "主营业务毛利率" },
	{ name: "资产负债率", value: 24.05, description: "总负债 / 总资产" },
	{ name: "流动比率", value: 4.16, description: "流动资产 / 流动负债" },
] as const;

// === 杜邦分析 ===

export const mockDupontAnalysis: DupontAnalysis = {
	roe: 8.98,
	netMargin: 47.3,
	assetTurnover: 0.14,
	equityMultiplier: 1.32,
};

// === 同行对比 ===

export const mockPeers: readonly PeerComparison[] = [
	{ code: "000858.SZ", name: "五粮液", pe: 22.8, pb: 6.5, roe: 28.5 },
	{ code: "002304.SZ", name: "洋河股份", pe: 18.2, pb: 4.8, roe: 26.3 },
	{ code: "000568.SZ", name: "泸州老窖", pe: 25.1, pb: 8.2, roe: 32.6 },
] as const;

// === 组合响应 ===

export const mockInstrumentFundamentals: GetInstrumentFundamentalsResponse = {
	income: mockIncome,
	balance: mockBalance,
	cashflow: mockCashflow,
	ratios: mockRatios,
	dupontAnalysis: mockDupontAnalysis,
	peers: mockPeers,
};
