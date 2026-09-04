import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DittoErrorBoundary, ErrorState } from "./error-boundary";

function ThrowingChild({ shouldThrow }: { readonly shouldThrow: boolean }) {
	if (shouldThrow) {
		throw new Error("Test error");
	}
	return <div>Normal content</div>;
}

describe("ErrorState", () => {
	// -- Rendering --

	it("renders with default title '加载失败'", () => {
		render(<ErrorState />);
		expect(screen.getByText("加载失败")).toBeInTheDocument();
	});

	it("renders with custom title", () => {
		render(<ErrorState title="网络超时" />);
		expect(screen.getByText("网络超时")).toBeInTheDocument();
	});

	it("renders with custom description", () => {
		render(<ErrorState description="请检查网络连接后重试" />);
		expect(screen.getByText("请检查网络连接后重试")).toBeInTheDocument();
	});

	it("renders without description when not provided", () => {
		const { container } = render(<ErrorState />);
		const description = container.querySelector("[data-testid='error-state-description']");
		expect(description).toBeNull();
	});

	it("renders error icon (40px circle)", () => {
		const { container } = render(<ErrorState />);
		const icon = container.querySelector("[data-testid='error-state-icon']");
		expect(icon).toBeInTheDocument();
		expect(icon).toHaveClass("w-10");
		expect(icon).toHaveClass("h-10");
		expect(icon).toHaveClass("rounded-full");
	});

	it("applies error icon background with led-error color at 10% opacity", () => {
		const { container } = render(<ErrorState />);
		const icon = container.querySelector("[data-testid='error-state-icon']");
		expect(icon).toBeInTheDocument();
		expect(icon!.className).toContain("bg-(--color-led-error)");
	});

	// -- Retry button --

	it("does not render retry button when onRetry is not provided", () => {
		render(<ErrorState />);
		expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
	});

	it("renders retry button when onRetry is provided", () => {
		const onRetry = vi.fn();
		render(<ErrorState onRetry={onRetry} />);
		expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
	});

	it("calls onRetry when retry button is clicked", async () => {
		const user = userEvent.setup();
		const onRetry = vi.fn();
		render(<ErrorState onRetry={onRetry} />);

		await user.click(screen.getByRole("button", { name: "重试" }));
		expect(onRetry).toHaveBeenCalledOnce();
	});

	// -- Data attributes --

	it("renders with data-slot attribute", () => {
		const { container } = render(<ErrorState />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "error-state");
	});

	// -- className merging --

	it("merges custom className", () => {
		const { container } = render(<ErrorState className="extra-class" />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveClass("extra-class");
	});
});

describe("DittoErrorBoundary", () => {
	// Suppress console.error from React error boundary
	const originalError = console.error;
	beforeAll(() => {
		console.error = vi.fn();
	});
	afterAll(() => {
		console.error = originalError;
	});

	it("renders children when no error occurs", () => {
		render(
			<DittoErrorBoundary>
				<ThrowingChild shouldThrow={false} />
			</DittoErrorBoundary>,
		);
		expect(screen.getByText("Normal content")).toBeInTheDocument();
	});

	it("renders ErrorState fallback when child throws", () => {
		render(
			<DittoErrorBoundary>
				<ThrowingChild shouldThrow />
			</DittoErrorBoundary>,
		);
		expect(screen.getByText("加载失败")).toBeInTheDocument();
	});

	it("renders custom ErrorState props when provided via fallbackProps", () => {
		render(
			<DittoErrorBoundary fallbackProps={{ title: "自定义错误", description: "出错了" }}>
				<ThrowingChild shouldThrow />
			</DittoErrorBoundary>,
		);
		expect(screen.getByText("自定义错误")).toBeInTheDocument();
		expect(screen.getByText("出错了")).toBeInTheDocument();
	});
});
