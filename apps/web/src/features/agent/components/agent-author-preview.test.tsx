import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentApprovalView } from "../types";
import { AgentAuthorPreview } from "./agent-author-preview";

const approval: AgentApprovalView = {
	approvalId: "approval-author-1",
	runId: "run-author-1",
	actionType: "strategy_patch",
	targetIdentity: "strategy-12@4",
	actionPayload: {
		action_kind: "strategy_patch",
		subject_identity: "strategy-12@4",
		parameters: {
			patch: [
				{ op: "replace", path: "/name", before: "Momentum v4", value: "Momentum v5" },
				{ op: "add", path: "/tags/2", value: "agent-reviewed" },
			],
			evidence_refs: ["evidence-7"],
			artifact_hash: "c".repeat(64),
			validation: { valid: true },
			guardrail: { status: "passed" },
		},
	},
	actionHash: "b".repeat(64),
	status: "pending",
	requestedAt: "2026-08-18T01:00:00Z",
	expiresAt: "2026-08-18T01:30:00Z",
	operatorId: null,
	reason: null,
	decidedAt: null,
};

describe("AgentAuthorPreview", () => {
	it("renders exact field changes and governance evidence as preview-only", () => {
		render(<AgentAuthorPreview approval={approval} />);

		expect(screen.getByText("PREVIEW ONLY · NOT APPLIED")).toBeInTheDocument();
		expect(screen.getByRole("cell", { name: "/name" })).toBeInTheDocument();
		expect(screen.getByRole("cell", { name: "Momentum v4" })).toBeInTheDocument();
		expect(screen.getByRole("cell", { name: "Momentum v5" })).toBeInTheDocument();
		expect(screen.getByText("evidence-7")).toBeInTheDocument();
		expect(screen.getByText("c".repeat(64))).toBeInTheDocument();
		expect(screen.getByText(/strategy-12@4/)).toBeInTheDocument();
	});
});
