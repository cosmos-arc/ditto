import type { LogicalRange, Time } from "lightweight-charts";

/**
 * 跨 cockpit 实例联动注册表：同一 rangeId 的图表同步可见逻辑区间与十字线时间戳。
 * cockpit 内部多 pane（价格/成交量）由单一 lightweight-charts 实例天然联动；
 * 本注册表覆盖页面级「多张独立图表共享时间范围」的合同（data-chart-linked-time-range）。
 */

export type RangeGroupMember = {
	readonly id: string;
	applyVisibleRange(range: LogicalRange): void;
	onLinkedCrosshair(time: Time | null): void;
};

const groups = new Map<string, Set<RangeGroupMember>>();

export function joinRangeGroup(rangeId: string, member: RangeGroupMember): () => void {
	let group = groups.get(rangeId);
	if (!group) {
		group = new Set();
		groups.set(rangeId, group);
	}
	group.add(member);
	return () => {
		group?.delete(member);
		if (group && group.size === 0) {
			groups.delete(rangeId);
		}
	};
}

export function broadcastVisibleRange(rangeId: string, originId: string, range: LogicalRange): void {
	for (const member of groups.get(rangeId) ?? []) {
		if (member.id !== originId) {
			member.applyVisibleRange(range);
		}
	}
}

export function broadcastCrosshairTime(rangeId: string, originId: string, time: Time | null): void {
	for (const member of groups.get(rangeId) ?? []) {
		if (member.id !== originId) {
			member.onLinkedCrosshair(time);
		}
	}
}
