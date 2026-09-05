import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockNodeDescriptorList } from "@/mocks/fixtures/strategy-live";
import type { StrategySpec } from "@/types/strategy";
import { mapNodeDescriptor } from "../api/mappers";
import { StrategyPipelineView } from "./strategy-pipeline-view";

const DESCRIPTORS = mockNodeDescriptorList.map(mapNodeDescriptor);

function baseSpec(constraints: StrategySpec["constraints"] = []): StrategySpec {
	return {
		strategyId: "s",
		name: "n",
		template: "t",
		universe: "u",
		assetClass: "etf",
		benchmark: "",
		scorer: { method: "m", params: {} },
		selector: { method: "m", params: {} },
		execution: { frequency: "M", method: "calendar", defaultOrderType: "market" },
		constraints,
		params: {},
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: [],
	};
}

function updaterAt(mock: ReturnType<typeof vi.fn>, index: number): (draft: StrategySpec) => StrategySpec {
	const updater: unknown = mock.mock.calls[index]?.[0];
	if (typeof updater !== "function") throw new Error(`expected updater call at index ${index}`);
	return updater as (draft: StrategySpec) => StrategySpec;
}

describe("StrategyPipelineView", () => {
	it("keeps fixed slots in grammar order with generated predecessor/successor rules", () => {
		const { container } = render(
			<StrategyPipelineView
				spec={baseSpec()}
				descriptors={DESCRIPTORS}
				onChange={vi.fn()}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		const rows = container.querySelectorAll("[data-fixed='true']");
		expect(Array.from(rows).map((row) => row.getAttribute("data-allowed-successor"))).toEqual([
			"FACTOR_SET",
			"FILTER",
			"SELECTOR",
			"ALLOCATOR",
			"EXECUTION_ASSUMPTION",
			"VALIDATION",
			null,
		]);
	});

	it("removes and reorders only registered FILTER nodes", () => {
		const onChange = vi.fn();
		const spec = baseSpec([
			{ type: "builtin.trend_filter@1", params: { threshold: 0 } },
			{ type: "builtin.trend_filter@1", params: { threshold: 1 } },
		]);
		render(
			<StrategyPipelineView
				spec={spec}
				descriptors={DESCRIPTORS}
				onChange={onChange}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		const moveButton = screen.getAllByLabelText("下移 Trend Filter")[0];
		if (!moveButton) throw new Error("expected move button");
		fireEvent.click(moveButton);
		const move = updaterAt(onChange, 0);
		expect(move(spec).constraints[0]?.params["threshold"]).toBe(1);

		const removeButton = screen.getAllByLabelText("删除 Trend Filter")[0];
		if (!removeButton) throw new Error("expected remove button");
		fireEvent.click(removeButton);
		const remove = updaterAt(onChange, 1);
		expect(remove(spec).constraints).toHaveLength(1);
	});

	it("supports Alt+Arrow keyboard reorder", () => {
		const onChange = vi.fn();
		const spec = baseSpec([
			{ type: "builtin.trend_filter@1", params: { threshold: 0 } },
			{ type: "builtin.trend_filter@1", params: { threshold: 1 } },
		]);
		render(
			<StrategyPipelineView
				spec={spec}
				descriptors={DESCRIPTORS}
				onChange={onChange}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		const filterButton = screen.getAllByRole("button", { name: /Trend Filter/ })[0];
		if (!filterButton) throw new Error("expected filter button");
		fireEvent.keyDown(filterButton, { key: "ArrowDown", altKey: true });
		expect(onChange).toHaveBeenCalledOnce();
	});

	it("renders an unknown descriptor read-only without a delete action", () => {
		render(
			<StrategyPipelineView
				spec={baseSpec([{ type: "plugin.unknown@9", params: { alpha: 1 } }])}
				descriptors={DESCRIPTORS}
				onChange={vi.fn()}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		expect(screen.getByText("未知 descriptor，只读")).toBeInTheDocument();
		expect(screen.queryByLabelText(/删除 plugin.unknown/)).not.toBeInTheDocument();
	});

	it("preserves every fixed slot as read-only when the registry response is incomplete", () => {
		const { container } = render(
			<StrategyPipelineView
				spec={baseSpec()}
				descriptors={[]}
				onChange={vi.fn()}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		expect(container.querySelectorAll("[data-fixed='true']")).toHaveLength(7);
		expect(container.querySelectorAll("[data-read-only='true']")).toHaveLength(7);
	});
});
