import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { mockActivePointerDto, mockVersionStateDto } from "@/mocks/fixtures/strategy-live";
import { server } from "@/mocks/server";
import { ReviewDecisionPanel } from "./review-decision-panel";

function createWrapper() {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

function renderPanel(
	reviewOutcome: string,
	hardReviewBlocked = false,
	bundleHash = "b".repeat(64),
	experimentId = "experiment-1",
) {
	render(
		<ReviewDecisionPanel
			strategyId="s"
			version={1}
			reviewOutcome={reviewOutcome}
			hardReviewBlocked={hardReviewBlocked}
			bundleHash={bundleHash}
			experimentId={experimentId}
		/>,
		{ wrapper: createWrapper() },
	);
}

describe("ReviewDecisionPanel", () => {
	it("pending outcome shows approve and reject, no publish", () => {
		renderPanel("pending");
		expect(screen.getByRole("button", { name: "批准" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "驳回" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
	});

	it("hard-gate blocked pending outcome disables approve but preserves reject", () => {
		renderPanel("pending", true);
		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "驳回" })).toBeEnabled();
	});

	it("approved outcome with hard-gate passed shows publish and deprecate", () => {
		renderPanel("approved", false);
		expect(screen.getByRole("button", { name: "发布" })).toBeEnabled();
		expect(screen.getByRole("button", { name: "弃用" })).toBeInTheDocument();
	});

	it("approved outcome with hard-gate blocked disables publish", () => {
		renderPanel("approved", true);
		expect(screen.getByRole("button", { name: "发布" })).toBeDisabled();
	});

	it("other outcome shows no action buttons", () => {
		renderPanel("rejected");
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
		expect(screen.getByRole("link", { name: "克隆为新草稿" })).toHaveAttribute("href", "/research/strategies/s/studio");
	});

	it("explains an unknown terminal outcome without inventing a governance action", () => {
		renderPanel("superseded");
		expect(screen.getByText("当前结论 superseded，无可执行动作。")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /批准|驳回|发布|弃用/ })).not.toBeInTheDocument();
	});

	it.each([
		{ action: "批准", confirm: "确认批准", endpoint: "approve", expectedTitle: "批准审查" },
		{ action: "驳回", confirm: "确认驳回", endpoint: "reject", expectedTitle: "驳回审查" },
	] as const)("submits a trimmed $endpoint decision through its governed endpoint", async (scenario) => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post(`/api/v1/strategies/s/versions/1/${scenario.endpoint}`, async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: mockVersionStateDto });
			}),
		);
		renderPanel("pending");

		await user.click(screen.getByRole("button", { name: scenario.action }));
		expect(screen.getByRole("heading", { name: scenario.expectedTitle })).toBeInTheDocument();
		await user.type(screen.getByLabelText("执行者"), "  reviewer  ");
		await user.type(screen.getByLabelText("原因"), "  evidence verified  ");
		await user.click(screen.getByRole("button", { name: scenario.confirm }));

		await waitFor(() => {
			expect(requestBody).toEqual({ actor: "reviewer", reason: "evidence verified" });
		});
		expect(screen.queryByRole("heading", { name: scenario.expectedTitle })).not.toBeInTheDocument();
	});

	it("submits deprecation as a distinct destructive decision", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/strategies/s/versions/1/deprecate", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: mockVersionStateDto });
			}),
		);
		renderPanel("approved");

		await user.click(screen.getByRole("button", { name: "弃用" }));
		await user.type(screen.getByLabelText("执行者"), "operator");
		await user.type(screen.getByLabelText("原因"), "superseded by reviewed version");
		await user.click(screen.getByRole("button", { name: "确认弃用" }));

		await waitFor(() => {
			expect(requestBody).toEqual({ actor: "operator", reason: "superseded by reviewed version" });
		});
	});

	it("publishes only after the operator confirms the exact version and persisted bundle hash", async () => {
		const user = userEvent.setup();
		const bundleHash = "c".repeat(64);
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/strategies/s/versions/1/publish", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: mockActivePointerDto });
			}),
		);
		renderPanel("approved", false, bundleHash);

		await user.click(screen.getByRole("button", { name: "发布" }));
		const confirm = screen.getByRole("button", { name: "确认发布" });
		expect(confirm).toBeDisabled();
		expect(screen.getByTitle(bundleHash)).toHaveTextContent(`${bundleHash.slice(0, 12)}…${bundleHash.slice(-8)}`);
		await user.type(screen.getByLabelText("执行者"), "publisher");
		await user.type(screen.getByLabelText("原因"), "review packet accepted");
		await user.type(screen.getByLabelText("确认句"), "发布 v1");
		expect(confirm).toBeEnabled();
		await user.click(confirm);

		await waitFor(() => {
			expect(requestBody).toEqual({
				actor: "publisher",
				bundle_hash: bundleHash,
				reason: "review packet accepted",
			});
		});
	});

	it("lets the reviewer dismiss a decision without issuing a command", async () => {
		const user = userEvent.setup();
		renderPanel("pending");

		await user.click(screen.getByRole("button", { name: "驳回" }));
		await user.click(screen.getByRole("button", { name: "取消" }));

		expect(screen.queryByRole("heading", { name: "驳回审查" })).not.toBeInTheDocument();
	});
});
