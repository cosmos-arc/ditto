import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ContextActions, ContextActionsProvider, type ContextActionsRequest } from "./context-actions";

const request = {
	contextId: "strategy-7@3",
	contextType: "strategy-version",
	evidenceObjective: "复核策略证据",
} as const;

describe("ContextActions", () => {
	it("fails closed without a composition-provided renderer", () => {
		const view = render(<ContextActions {...request} />);

		expect(view.container).toBeEmptyDOMElement();
	});

	it("passes the exact context to the renderer supplied by app composition", () => {
		const renderActions = vi.fn((value: ContextActionsRequest) => (
			<a href={`/context/${value.contextType}/${value.contextId}`}>分析证据</a>
		));

		render(
			<ContextActionsProvider renderActions={renderActions}>
				<ContextActions {...request} />
			</ContextActionsProvider>,
		);

		expect(renderActions).toHaveBeenCalledWith(request);
		expect(screen.getByRole("link", { name: "分析证据" })).toHaveAttribute(
			"href",
			"/context/strategy-version/strategy-7@3",
		);
	});
});
