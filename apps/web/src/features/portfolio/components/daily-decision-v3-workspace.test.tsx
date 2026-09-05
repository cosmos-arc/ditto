import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createDailyDecisionV3ViewModel } from "./daily-decision-v3.fixture";
import { DailyDecisionV3Workspace } from "./daily-decision-v3-workspace";

describe("DailyDecisionV3Workspace", () => {
	it("renders the ready cockpit with risk headline, provenance, and actions", () => {
		const baseAction = createDailyDecisionV3ViewModel().actions[0];
		if (!baseAction) throw new Error("expected daily-decision action fixture");
		const decision = createDailyDecisionV3ViewModel({
			actions: [
				{
					...baseAction,
					filledQuantity: 250,
					remainingQuantity: 750,
					riskFlags: ["LIMIT_UP", "CONCENTRATION_REVIEW"],
					sizingReadiness: "review",
				},
			],
		});
		const { container } = render(<DailyDecisionV3Workspace decision={decision} />);

		expect(screen.getByText("可执行")).toBeInTheDocument();
		expect(screen.getByText("Historical ES99")).toBeInTheDocument();
		expect(screen.getByText("4.10%")).toBeInTheDocument();
		expect(screen.getByText("#510300")).toBeInTheDocument();
		expect(screen.getByText("review")).toBeInTheDocument();
		expect(screen.getByText("LIMIT_UP")).toBeInTheDocument();
		expect(screen.getByText("CONCENTRATION_REVIEW")).toBeInTheDocument();
		expect(screen.getByText("250 / 1,000")).toBeInTheDocument();
		expect(screen.getByText("剩余 750 · pending")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='decision-readiness']")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='decision-actions']")).toBeInTheDocument();
	});

	it("distinguishes review from ready", () => {
		const decision = createDailyDecisionV3ViewModel({
			readiness: { status: "review", reportedStatus: "review", blockingReasons: ["MANUAL_REVIEW_REQUIRED"] },
		});
		render(<DailyDecisionV3Workspace decision={decision} />);

		expect(screen.getByText("需人工复核")).toBeInTheDocument();
		expect(screen.queryByText("可执行")).not.toBeInTheDocument();
	});

	it("closes all execution affordance when blocked", () => {
		const decision = createDailyDecisionV3ViewModel({
			readiness: { status: "blocked", reportedStatus: "blocked", blockingReasons: ["PIT_PROVENANCE_INCOMPLETE"] },
		});
		render(<DailyDecisionV3Workspace decision={decision} />);

		const blocker = screen.getByRole("alert");
		expect(within(blocker).getByText("交易动作关闭")).toBeInTheDocument();
		expect(screen.queryByText("可执行")).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /执行/u })).not.toBeInTheDocument();
	});

	it("marks stale data without presenting it as the current identity", () => {
		const decision = createDailyDecisionV3ViewModel({
			data: { freshness: "stale", qualityState: "passed", snapshotIds: { bars: "old-snapshot" } },
		});
		render(<DailyDecisionV3Workspace decision={decision} />);

		expect(screen.getByText("数据已过期")).toBeInTheDocument();
		expect(screen.getByText("old-snapshot")).toBeInTheDocument();
	});

	it("names partial evidence instead of hiding unavailable modules", () => {
		const decision = createDailyDecisionV3ViewModel({
			completeness: { status: "partial", issues: ["FACTOR_RISK_PARTIAL"] },
		});
		render(<DailyDecisionV3Workspace decision={decision} />);

		expect(screen.getByText("部分风险证据不可用")).toBeInTheDocument();
		expect(screen.getByText("FACTOR_RISK_PARTIAL")).toBeInTheDocument();
	});
});
