/** 回测买卖点下钻上下文（跨域跳转合同）：定位日、来源 run、知识时间、买卖方向。 */
export interface InstrumentDrillContext {
	readonly date: string;
	readonly runId: string;
	readonly asOf: string;
	readonly direction: "buy" | "sell";
}
