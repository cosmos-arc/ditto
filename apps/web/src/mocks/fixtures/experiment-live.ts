/**
 * R3 live-shape experiment mocks（generated `ExperimentSummaryResponse` 形态）。
 *
 * T18 仅接线 experiment 列表；完整工作台属 T19。与 {@link "./research"} 中的
 * prototype mock（旧 `Experiment` 形状）并存，组件迁移完成后清理。
 */
import type { components } from "@/types/generated/api";

type ExperimentSummaryResponse = components["schemas"]["ExperimentSummaryResponse"];

export const mockExperimentSummaryList: ExperimentSummaryResponse[] = [
	{
		experiment_id: "exp-1042",
		status: "running",
		desired_state: "running",
		stage: "candidate_evaluation",
		failure_code: null,
		queue_ordinal: 1,
		revision: 3,
		created_at: "2026-07-20T08:00:00Z",
		updated_at: "2026-07-29T14:00:00Z",
	},
	{
		experiment_id: "exp-1039",
		status: "queued",
		desired_state: "running",
		stage: "pending",
		failure_code: null,
		queue_ordinal: 2,
		revision: 1,
		created_at: "2026-07-22T10:30:00Z",
		updated_at: "2026-07-22T10:30:00Z",
	},
	{
		experiment_id: "exp-1035",
		status: "completed",
		desired_state: "completed",
		stage: "finalized",
		failure_code: null,
		queue_ordinal: null,
		revision: 5,
		created_at: "2026-07-10T09:00:00Z",
		updated_at: "2026-07-15T16:00:00Z",
	},
];
