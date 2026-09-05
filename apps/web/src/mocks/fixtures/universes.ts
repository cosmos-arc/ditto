import type { UniverseResponse } from "@/features/research/api/universes";

export const mockUniverseDefinitions: UniverseResponse[] = [
	{
		universe_id: "csi300",
		name: "沪深 300",
		universe_type: "preset",
		description: "官方宽基指数范围；成员必须按显式 as-of 查询。",
		source_ref: "index:csi300",
	},
	{
		universe_id: "csi_etf_broad",
		name: "A 股宽基 ETF",
		universe_type: "preset",
		description: "研究与回测共用的宽基 ETF 预设范围。",
		source_ref: "catalog:csi-etf-broad",
	},
	{
		universe_id: "etf_core_watch",
		name: "ETF 核心观察池",
		universe_type: "custom",
		description: "本机单操作者维护的核心观察范围。",
		source_ref: null,
	},
];

export const mockUniverseMembers: Readonly<Record<string, readonly number[]>> = {
	csi300: [600519, 601318, 600036],
	csi_etf_broad: [510300, 510500, 159915],
	etf_core_watch: [510300, 510500],
};
