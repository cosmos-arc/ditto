import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DecisionDialog, ReactivateDialog, reactivateConfirmation } from "./governance-dialogs";

describe("DecisionDialog", () => {
	it("disables confirm until actor and reason are both non-empty", () => {
		render(
			<DecisionDialog
				open
				onOpenChange={vi.fn()}
				title="提交审查"
				confirmLabel="确认提交"
				isPending={false}
				onConfirm={vi.fn()}
			/>,
		);
		expect(screen.getByRole("button", { name: "确认提交" })).toBeDisabled();

		fireEvent.change(screen.getByLabelText("执行者"), { target: { value: "analyst" } });
		fireEvent.change(screen.getByLabelText("原因"), { target: { value: "提交审查" } });

		expect(screen.getByRole("button", { name: "确认提交" })).not.toBeDisabled();
	});

	it("calls onConfirm with trimmed actor and reason", () => {
		const onConfirm = vi.fn();
		render(
			<DecisionDialog
				open
				onOpenChange={vi.fn()}
				title="批准"
				confirmLabel="确认批准"
				isPending={false}
				onConfirm={onConfirm}
			/>,
		);
		fireEvent.change(screen.getByLabelText("执行者"), { target: { value: "analyst" } });
		fireEvent.change(screen.getByLabelText("原因"), { target: { value: "通过" } });
		fireEvent.click(screen.getByRole("button", { name: "确认批准" }));

		expect(onConfirm).toHaveBeenCalledWith("analyst", "通过");
	});
});

describe("ReactivateDialog", () => {
	it("derives the exact server confirmation from strategy, version, and pointer revision", () => {
		expect(reactivateConfirmation("s", 3, 2)).toBe("strategy:reactivate:s@3:pointer-revision:2:confirm");
	});

	it("disables confirm until the confirmation phrase matches the target version", () => {
		render(
			<ReactivateDialog
				open
				onOpenChange={vi.fn()}
				strategyId="s"
				targetVersion={3}
				expectedPointerRevision={2}
				isPending={false}
				onConfirm={vi.fn()}
			/>,
		);
		fireEvent.change(screen.getByLabelText("执行者"), { target: { value: "analyst" } });
		fireEvent.change(screen.getByLabelText("原因"), { target: { value: "切回 v3" } });
		fireEvent.change(screen.getByLabelText("影响摘要"), { target: { value: "回滚到已验证版本" } });

		expect(screen.getByRole("button", { name: "确认重新激活" })).toBeDisabled();

		fireEvent.change(screen.getByLabelText("确认句"), {
			target: { value: "strategy:reactivate:s@3:pointer-revision:2:confirm" },
		});
		expect(screen.getByRole("button", { name: "确认重新激活" })).not.toBeDisabled();
	});

	it("calls onConfirm with expected_pointer_revision when confirmed", () => {
		const onConfirm = vi.fn();
		render(
			<ReactivateDialog
				open
				onOpenChange={vi.fn()}
				strategyId="s"
				targetVersion={3}
				expectedPointerRevision={2}
				isPending={false}
				onConfirm={onConfirm}
			/>,
		);
		fireEvent.change(screen.getByLabelText("执行者"), { target: { value: "analyst" } });
		fireEvent.change(screen.getByLabelText("原因"), { target: { value: "切回 v3" } });
		fireEvent.change(screen.getByLabelText("影响摘要"), { target: { value: "回滚" } });
		fireEvent.change(screen.getByLabelText("确认句"), {
			target: { value: "strategy:reactivate:s@3:pointer-revision:2:confirm" },
		});
		fireEvent.click(screen.getByRole("button", { name: "确认重新激活" }));

		expect(onConfirm).toHaveBeenCalledWith(
			expect.objectContaining({
				version: 3,
				expectedPointerRevision: 2,
				confirmation: "strategy:reactivate:s@3:pointer-revision:2:confirm",
			}),
		);
	});
});
