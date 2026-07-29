/**
 * Strategy Studio 编辑工作副本 store（Zustand 客户端状态）。
 *
 * 职责分离原则：服务端真理由 TanStack Query（`useStrategy`）持有；本 store 只持有
 * 编辑期的工作副本（`workingSpec`）、已保存快照（`savedSpec`，用于 dirty 判定）、
 * 编辑模式与选中节点等纯 UI 状态。
 *
 * - `loadSpec`：从 server 加载 spec，同步 working/saved，清除 dirty。
 * - `updateSpec`：修改 working 副本（不可变更新），触发 dirty。
 * - `resetWorking`：放弃编辑，working 回退到 saved。
 * - dirty 由 `workingSpec` 与 `savedSpec` 的结构相等判定（JSON 可序列化）。
 */
import { create } from "zustand";
import type { StrategySpec } from "@/types/strategy";

export type StudioMode = "form" | "code";

interface StrategyStudioState {
	readonly workingSpec: StrategySpec | null;
	readonly savedSpec: StrategySpec | null;
	readonly mode: StudioMode;
	readonly selectedNodeKey: string | null;
	loadSpec: (spec: StrategySpec) => void;
	updateSpec: (updater: (draft: StrategySpec) => StrategySpec) => void;
	resetWorking: () => void;
	setMode: (mode: StudioMode) => void;
	selectNode: (key: string | null) => void;
}

export const useStrategyStudioStore = create<StrategyStudioState>((set, get) => ({
	workingSpec: null,
	savedSpec: null,
	mode: "form",
	selectedNodeKey: null,
	loadSpec: (spec) => set({ workingSpec: spec, savedSpec: spec, selectedNodeKey: null }),
	updateSpec: (updater) => {
		const current = get().workingSpec;
		if (!current) return;
		set({ workingSpec: updater(current) });
	},
	resetWorking: () => {
		const saved = get().savedSpec;
		if (saved) set({ workingSpec: saved, selectedNodeKey: null });
	},
	setMode: (mode) => set({ mode }),
	selectNode: (key) => set({ selectedNodeKey: key }),
}));

/** dirty 派生 selector：working 与 saved 的结构不一致即脏。 */
export function selectIsDirty(state: StrategyStudioState): boolean {
	const { workingSpec, savedSpec } = state;
	if (!workingSpec || !savedSpec) return false;
	return JSON.stringify(workingSpec) !== JSON.stringify(savedSpec);
}
