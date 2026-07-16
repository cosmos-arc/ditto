import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DittoTooltip, DittoTooltipContent, DittoTooltipTrigger } from "./tooltip";

/** Helper: 渲染完整的 Tooltip 组合，返回 tooltip 内容元素 */
function renderTooltip(
	content: string,
	triggerLabel: string,
	contentProps?: React.ComponentProps<typeof DittoTooltipContent>,
) {
	const result = render(
		<DittoTooltip open>
			<DittoTooltipTrigger>{triggerLabel}</DittoTooltipTrigger>
			<DittoTooltipContent {...contentProps}>{content}</DittoTooltipContent>
		</DittoTooltip>,
	);
	// Radix Tooltip 在 Portal 中渲染 content，需从 document.body 查询
	const tooltipSlot = document.body.querySelector("[data-slot='tooltip']");
	return { ...result, tooltipSlot: tooltipSlot as HTMLElement };
}

describe("DittoTooltip", () => {
	it("exports DittoTooltip, DittoTooltipTrigger, DittoTooltipContent", () => {
		expect(DittoTooltip).toBeDefined();
		expect(DittoTooltipTrigger).toBeDefined();
		expect(DittoTooltipContent).toBeDefined();
	});

	it("renders content text when open", () => {
		const { tooltipSlot } = renderTooltip("Hello tooltip", "Hover me");
		expect(tooltipSlot).toBeTruthy();
		expect(tooltipSlot.textContent).toContain("Hello tooltip");
	});

	it("renders trigger text", () => {
		renderTooltip("Hello tooltip", "Hover me");
		expect(screen.getByRole("button", { name: "Hover me" })).toBeInTheDocument();
	});
});

describe("DittoTooltipContent", () => {
	it("has data-slot='tooltip' attribute", () => {
		const { tooltipSlot } = renderTooltip("Test content", "Trigger");
		expect(tooltipSlot).toBeTruthy();
		expect(tooltipSlot.getAttribute("data-slot")).toBe("tooltip");
	});

	it("applies Graphite Studio base styles", () => {
		const { tooltipSlot } = renderTooltip("Styled content", "Trigger");
		const classStr = tooltipSlot.classList.toString();
		// border 样式
		expect(classStr).toContain("border");
		// bg-(--color-surface-overlay)
		expect(classStr).toContain("bg-(--color-surface-overlay)");
		// text-xs 排版
		expect(classStr).toContain("text-xs");
		// max-w-[240px]
		expect(classStr).toContain("max-w-[240px]");
		// shadow
		expect(classStr).toContain("shadow-[0_4px_12px_oklch(0_0_0/0.3)]");
	});

	it("merges custom className", () => {
		const { tooltipSlot } = renderTooltip("Custom", "Trigger", {
			className: "extra-class",
		});
		expect(tooltipSlot.classList.contains("extra-class")).toBe(true);
	});

	it("defaults side to 'top'", () => {
		const { tooltipSlot } = renderTooltip("Default side", "Trigger");
		// Radix 通过 data-side 属性标记方向
		expect(tooltipSlot.getAttribute("data-side")).toBe("top");
	});

	it("passes custom side prop", () => {
		const { tooltipSlot } = renderTooltip("Bottom side", "Trigger", {
			side: "bottom",
		});
		expect(tooltipSlot.getAttribute("data-side")).toBe("bottom");
	});

	it("passes custom sideOffset prop without crash", () => {
		const { tooltipSlot } = renderTooltip("Offset", "Trigger", {
			sideOffset: 12,
		});
		// sideOffset 通过 Radix 内部样式应用，确认组件不崩溃且渲染正确
		expect(tooltipSlot).toBeTruthy();
	});

	it("applies fade-in animation classes", () => {
		const { tooltipSlot } = renderTooltip("Animated", "Trigger");
		const classStr = tooltipSlot.classList.toString();
		expect(classStr).toContain("data-[state=open]:animate-in");
		expect(classStr).toContain("data-[state=closed]:animate-out");
	});
});
