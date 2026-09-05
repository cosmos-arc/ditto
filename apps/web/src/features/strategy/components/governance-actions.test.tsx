import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import type { StrategyLifecycleState, StrategyVersion } from "@/types/strategy";
import { GovernanceActions, type StrategyReviewEvidence } from "./governance-actions";

function makeVersion(lifecycleState: StrategyLifecycleState, version = 1): StrategyVersion {
	return {
		strategyId: "s",
		version,
		parentVersion: null,
		specHash: "h",
		state: lifecycleState,
		lifecycleState,
		reviewOutcome: "pending",
		createdAt: "2026-01-01T00:00:00Z",
		experimentId: "exp-gov",
	};
}

function createWrapper() {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

function reviewEvidence(hardReviewBlocked = false): StrategyReviewEvidence {
	return hardReviewBlocked
		? {
				bundleHash: "d".repeat(64),
				hardReviewBlocked: true,
				issue: {
					code: "REVIEW_HARD_GATE_BLOCKED",
					message: "review packet hard gates 未通过",
				},
			}
		: { bundleHash: "d".repeat(64), hardReviewBlocked: false, issue: null };
}

function renderActions(
	lifecycleState: StrategyLifecycleState,
	expectedPointerRevision: number | null = null,
	version = 1,
	hardReviewBlocked = false,
) {
	render(
		<GovernanceActions
			strategyId="s"
			version={makeVersion(lifecycleState, version)}
			expectedPointerRevision={expectedPointerRevision}
			currentActiveVersion={4}
			reviewEvidence={reviewEvidence(hardReviewBlocked)}
		/>,
		{ wrapper: createWrapper() },
	);
}

async function fillReactivateDialog(): Promise<void> {
	const user = userEvent.setup();
	await user.click(screen.getByRole("button", { name: "重新激活" }));
	await user.type(screen.getByLabelText("执行者"), "analyst");
	await user.type(screen.getByLabelText("原因"), "切回已验证版本");
	await user.type(screen.getByLabelText("影响摘要"), "恢复稳定策略");
	await user.type(screen.getByLabelText("确认句"), "strategy:reactivate:s@3:pointer-revision:2:confirm");
}

describe("GovernanceActions", () => {
	it("draft state shows a submit-review action", () => {
		renderActions("draft");
		expect(screen.getByRole("button", { name: "提交审查" })).toBeInTheDocument();
	});

	it("hard-gate blocked draft keeps submit disabled", async () => {
		renderActions("draft", null, 1, true);
		expect(await screen.findByRole("button", { name: "提交审查" })).toBeDisabled();
	});

	it("fails closed with a structured issue when review evidence is missing", () => {
		render(
			<GovernanceActions
				strategyId="s"
				version={{ ...makeVersion("draft"), experimentId: null }}
				expectedPointerRevision={null}
				currentActiveVersion={4}
				reviewEvidence={{
					bundleHash: null,
					hardReviewBlocked: true,
					issue: {
						code: "REVIEW_PACKET_MISSING",
						message: "当前策略版本没有绑定 review packet",
					},
				}}
			/>,
			{ wrapper: createWrapper() },
		);

		expect(screen.getByRole("button", { name: "提交审查" })).toBeDisabled();
		expect(screen.getByRole("alert")).toHaveTextContent("REVIEW_PACKET_MISSING: 当前策略版本没有绑定 review packet");
	});

	it("review state shows approve and reject actions", () => {
		renderActions("review");
		expect(screen.getByRole("button", { name: "批准" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "驳回" })).toBeInTheDocument();
	});

	it("rejected review state is clone-only", () => {
		const rejected = { ...makeVersion("review"), reviewOutcome: "rejected" as const };
		render(
			<GovernanceActions
				strategyId="s"
				version={rejected}
				expectedPointerRevision={2}
				currentActiveVersion={4}
				reviewEvidence={reviewEvidence()}
			/>,
			{ wrapper: createWrapper() },
		);
		expect(screen.getByRole("link", { name: "克隆为新草稿" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "驳回" })).not.toBeInTheDocument();
	});

	it("approved state shows deprecate only (publish lives on review-detail)", () => {
		renderActions("approved");
		expect(screen.getByRole("button", { name: "弃用" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
	});

	it("published state with a pointer revision shows reactivate", () => {
		renderActions("published", 2);
		expect(screen.getByRole("button", { name: "重新激活" })).toBeInTheDocument();
	});

	it("published state without a pointer revision hides reactivate", () => {
		renderActions("published", null);
		expect(screen.queryByRole("button", { name: "重新激活" })).not.toBeInTheDocument();
	});

	it("deprecated state shows no actions", () => {
		renderActions("deprecated");
		expect(screen.queryByRole("button")).not.toBeInTheDocument();
	});

	it("clicking a decision action opens the dialog with confirm disabled until filled", async () => {
		renderActions("draft");
		await userEvent.click(screen.getByRole("button", { name: "提交审查" }));

		expect(screen.getByRole("heading", { name: "提交审查" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "确认提交" })).toBeDisabled();
	});

	it("keeps the reactivate dialog open until the mutation succeeds", async () => {
		let releaseResponse: (() => void) | undefined;
		const responseGate = new Promise<void>((resolve) => {
			releaseResponse = resolve;
		});
		server.use(
			http.post("/api/v1/strategies/s/versions/3/reactivate", async () => {
				await responseGate;
				return HttpResponse.json({ data: {} });
			}),
		);
		renderActions("published", 2, 3);
		await fillReactivateDialog();

		await userEvent.click(screen.getByRole("button", { name: "确认重新激活" }));

		expect(await screen.findByRole("heading", { name: "重新激活 v3" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "处理中…" })).toBeDisabled();

		await act(async () => {
			releaseResponse?.();
			await responseGate;
		});
		await waitFor(() => {
			expect(screen.queryByRole("heading", { name: "重新激活 v3" })).not.toBeInTheDocument();
		});
	});

	it("keeps all reactivate inputs after an HTTP 409", async () => {
		server.use(
			http.post("/api/v1/strategies/s/versions/3/reactivate", () =>
				HttpResponse.json(
					{ detail: "active pointer changed", error_code: "POINTER_REVISION_CONFLICT" },
					{ status: 409 },
				),
			),
		);
		renderActions("published", 2, 3);
		await fillReactivateDialog();

		await userEvent.click(screen.getByRole("button", { name: "确认重新激活" }));

		await waitFor(() => {
			expect(screen.getByRole("button", { name: "确认重新激活" })).not.toBeDisabled();
		});
		expect(screen.getByLabelText("执行者")).toHaveValue("analyst");
		expect(screen.getByLabelText("原因")).toHaveValue("切回已验证版本");
		expect(screen.getByLabelText("影响摘要")).toHaveValue("恢复稳定策略");
		expect(screen.getByLabelText("确认句")).toHaveValue("strategy:reactivate:s@3:pointer-revision:2:confirm");
		expect(screen.getByRole("alert")).toHaveTextContent(/409 POINTER_REVISION_CONFLICT/);
	});
});
