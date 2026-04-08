import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Drawer } from "./drawer";

describe("Drawer", () => {
	// ── Rendering ──

	it("renders nothing when open=false", () => {
		const { container } = render(
			<Drawer open={false} onClose={() => {}} title="Test">
				Content
			</Drawer>,
		);
		expect(container.innerHTML).toBe("");
	});

	it("renders title when open=true", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="市场深度">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			expect(screen.getByText("市场深度")).toBeInTheDocument();
		});
	});

	it("renders children content when open=true", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				<div>Body Content</div>
			</Drawer>,
		);
		await waitFor(() => {
			expect(screen.getByText("Body Content")).toBeInTheDocument();
		});
	});

	it("renders close button", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			const closeBtn = screen.getByRole("button", { name: /close/i });
			expect(closeBtn).toBeInTheDocument();
		});
	});

	// ── Props ──

	it("accepts custom width", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test" width="480px">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			const content = document.querySelector("[data-slot='sheet-content']") as HTMLElement;
			expect(content).toBeInTheDocument();
			expect(content.style.width).toBe("480px");
		});
	});

	it("uses default width 340px when not specified", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			const content = document.querySelector("[data-slot='sheet-content']") as HTMLElement;
			expect(content).toBeInTheDocument();
			expect(content.style.width).toBe("340px");
		});
	});

	// ── Close behavior ──

	it("calls onClose when close button is clicked", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		render(
			<Drawer open={true} onClose={onClose} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			expect(screen.getByRole("dialog")).toBeInTheDocument();
		});
		const closeBtn = screen.getByRole("button", { name: /close/i });
		await user.click(closeBtn);
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("calls onClose when Escape key is pressed", async () => {
		const onClose = vi.fn();
		render(
			<Drawer open={true} onClose={onClose} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			expect(screen.getByRole("dialog")).toBeInTheDocument();
		});
		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	// ── Accessibility ──

	it("renders with role=dialog", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			expect(screen.getByRole("dialog")).toBeInTheDocument();
		});
	});

	it("renders aria-label with title", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="市场深度">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			const dialog = screen.getByRole("dialog");
			expect(dialog).toHaveAttribute("aria-label", "市场深度");
		});
	});

	// ── Structure ──

	it("renders header with border bottom", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				Content
			</Drawer>,
		);
		await waitFor(() => {
			const header = document.querySelector("[data-slot='sheet-header']") as HTMLElement;
			expect(header).toBeInTheDocument();
			expect(header.className).toContain("border-b");
		});
	});

	it("renders body section", async () => {
		render(
			<Drawer open={true} onClose={() => {}} title="Test">
				<div>Body</div>
			</Drawer>,
		);
		await waitFor(() => {
			const body = document.querySelector("[data-slot='drawer-body']") as HTMLElement;
			expect(body).toBeInTheDocument();
		});
	});
});
