/**
 * R3 Review queue + review-packet view-models.
 *
 * 组件唯一消费的 camelCase 形态。mapper（`features/research/api/reviews.ts` /
 * `review-packet.ts`）负责 generated snake_case DTO → 此处 view-model 的翻译。
 *
 * 关键事实（设计依据）：
 * - review queue 项的 `experimentId` 是跨域桥接键（后端按 spec_hash 解析），
 *   `null` 表示该版本尚无持久化 review packet（review-detail 降级空态）。
 * - `hardReviewBlocked` 是 11 hard-gate 的聚合裁决；单 gate `outcome` 原样渲染，
 *   绝不伪造通过（治理核心原则）。
 * - 统计证据是**内容 hash**（objective/comparison/r1_impact payload hash），非 metric 值。
 */

/** Review queue 项（待审查 / 已批准待发布的版本）。 */
export type ReviewQueueEntry = {
	readonly strategyId: string;
	readonly version: number;
	readonly parentVersion: number | null;
	readonly specHash: string;
	readonly state: string;
	readonly reviewOutcome: string;
	readonly createdAt: string;
	/** 持有 review packet 的 experiment（按 spec_hash 桥接）；null = 尚无 packet。 */
	readonly experimentId: string | null;
};

/** 一条 hard-gate 裁决（rule_id / layer / outcome 原样来自后端）。 */
export type ReviewGate = {
	readonly ruleId: string;
	readonly layer: string;
	readonly outcome: string;
};

/** selection-trace artifact 引用（fold/attempt 证据链）。 */
export type SelectionTraceRef = {
	readonly artifactKind: string;
	readonly artifactId: string;
	readonly contentHash: string;
};

/** 完整 review packet read model（11 hard-gate + 证据 hash + lineage + rationale）。 */
export type ReviewPacket = {
	readonly experimentId: string;
	readonly candidateId: string | null;
	/** review packet 内容 hash —— evidence-gated publish 的证据身份。 */
	readonly bundleHash: string;
	readonly hardReviewBlocked: boolean;
	readonly gateOutcomes: readonly ReviewGate[];
	readonly schemaVersion: number;
	readonly foldIds: readonly string[];
	readonly attemptIds: readonly string[];
	readonly specHash: string;
	readonly resolvedSpecHash: string;
	readonly parameterHash: string;
	readonly snapshotHash: string;
	readonly registryHash: string;
	readonly objectivePayloadHash: string;
	readonly comparisonPayloadHash: string | null;
	readonly r1ImpactPayloadHash: string | null;
	readonly selectionEvidenceArtifactId: string | null;
	readonly holdoutClaimId: string | null;
	readonly candidateRationale: string;
	readonly selectionTraceArtifactRefs: readonly SelectionTraceRef[];
};
