import { create } from "zustand";
import { MAX_COMPARE_RUNS } from "../lib/multi-run-mapping";

const storageKey = "ditto.backtest-comparison.v1";
export const comparisonLifetime = "当前标签页会话集合：刷新保留，关闭标签页后结束；未保存到服务端。";

function restore(): { runIds: string[]; error: string | null } {
	try {
		const runIds: unknown = JSON.parse(sessionStorage.getItem(storageKey) ?? "[]");
		if (
			!Array.isArray(runIds) ||
			runIds.length > MAX_COMPARE_RUNS ||
			runIds.some((id) => typeof id !== "string" || !id.trim()) ||
			new Set(runIds).size !== runIds.length
		) {
			throw new Error("Invalid comparison session");
		}
		return { runIds, error: null };
	} catch {
		return { runIds: [], error: "无法恢复会话对比集合，请重新选择运行。" };
	}
}

export const useBacktestComparison = create<{
	readonly runIds: readonly string[];
	readonly error: string | null;
	readonly setIncluded: (runId: string, included: boolean) => boolean;
}>((set, get) => ({
	...restore(),
	setIncluded: (runId, included) => {
		const previous = get().runIds;
		if (previous.includes(runId) === included) return true;
		if (included && previous.length >= MAX_COMPARE_RUNS) {
			set({ error: `对比已达 ${MAX_COMPARE_RUNS} 个 run 上限，请先移除一个运行。` });
			return false;
		}
		const runIds = included ? [...previous, runId] : previous.filter((id) => id !== runId);
		try {
			// 先保存再公布变化；存储失败时保留原集合，用户可在恢复后重试。
			sessionStorage.setItem(storageKey, JSON.stringify(runIds));
			set({ runIds, error: null });
			return true;
		} catch {
			set({ error: "无法保存会话对比集合，本次变更未生效。请允许浏览器会话存储后重试。" });
			return false;
		}
	},
}));
