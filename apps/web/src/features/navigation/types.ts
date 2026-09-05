/** 5 大产品业务域定义；AI 作为嵌入式能力存在，不再作为独立产品域。 */
export interface Domain {
	/** 域标识 */
	readonly id: DomainId;
	/** 显示名称 */
	readonly label: string;
	/** 路由前缀 */
	readonly path: string;
}

export type DomainId = "home" | "markets" | "research" | "portfolio" | "system";

/** 所有域配置 */
export const DOMAINS: readonly Domain[] = [
	{ id: "home", label: "Today", path: "/" },
	{ id: "markets", label: "Markets", path: "/markets" },
	{ id: "research", label: "Research", path: "/research" },
	{ id: "portfolio", label: "Portfolio", path: "/portfolio" },
	{ id: "system", label: "System", path: "/system" },
] as const;
