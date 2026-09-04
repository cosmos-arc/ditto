import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { PageActionOverlay } from "./page-action-overlay";

function OverlayHarness() {
	const [open, setOpen] = useState(false);
	return (
		<>
			<button type="button" onClick={() => setOpen(true)}>
				打开测试弹层
			</button>
			<PageActionOverlay
				description="验证焦点闭环"
				kind="drawer"
				onClose={() => setOpen(false)}
				open={open}
				title="测试弹层"
			>
				<input aria-label="测试输入" />
			</PageActionOverlay>
		</>
	);
}

describe("PageActionOverlay", () => {
	it("通过 Escape 关闭后将焦点归还给触发按钮", async () => {
		const user = userEvent.setup();
		render(<OverlayHarness />);
		const trigger = screen.getByRole("button", { name: "打开测试弹层" });

		await user.click(trigger);
		await screen.findByRole("dialog", { name: "测试弹层" });
		await user.keyboard("{Escape}");

		await waitFor(() => expect(screen.queryByRole("dialog", { name: "测试弹层" })).not.toBeInTheDocument());
		expect(trigger).toHaveFocus();
	});
});
