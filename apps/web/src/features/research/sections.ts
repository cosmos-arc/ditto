export interface ResearchSection {
	/** 导航显示名称 */
	readonly label: string;
	/** 路由路径 */
	readonly path: string;
	/** 精确匹配（总览入口需精确，避免前缀命中所有子路由）；省略则前缀匹配 */
	readonly exact?: boolean;
}

/**
 * research 域主干分区入口。
 * 隐藏 node-descriptors（开发辅助占位页，不作为用户入口）。
 */
export const RESEARCH_SECTIONS: readonly ResearchSection[] = [
	{ label: "总览", path: "/research", exact: true },
	{ label: "股票池", path: "/research/universes" },
	{ label: "因子", path: "/research/factors" },
	{ label: "实验", path: "/research/experiments" },
	{ label: "回测", path: "/research/backtests" },
	{ label: "策略", path: "/research/strategies" },
	{ label: "Agent Lab", path: "/research/agent" },
	{ label: "审查", path: "/research/reviews" },
] as const;
