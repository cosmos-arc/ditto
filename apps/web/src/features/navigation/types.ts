/** 6 大业务域定义 */
export interface Domain {
	/** 域标识 */
	readonly id: DomainId;
	/** 显示名称 */
	readonly label: string;
	/** 路由前缀 */
	readonly path: string;
}

export type DomainId =
	| "home"
	| "markets"
	| "research"
	| "trading"
	| "ai"
	| "platform";

/** 所有域配置 */
export const DOMAINS: readonly Domain[] = [
	{ id: "home", label: "首页", path: "/" },
	{ id: "markets", label: "市场", path: "/markets" },
	{ id: "research", label: "研究", path: "/research" },
	{ id: "trading", label: "交易", path: "/trading" },
	{ id: "ai", label: "AI", path: "/ai" },
	{ id: "platform", label: "平台", path: "/platform" },
] as const;
