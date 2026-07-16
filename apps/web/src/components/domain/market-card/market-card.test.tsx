import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MarketCard } from "./market-card";

describe("MarketCard", () => {
	// ── Rendering ──

	it("renders market name", () => {
		render(<MarketCard name="A股 · 沪深300" regime="on" index="3,912.45" change={0.67} judgment="涨跌比偏强" />);
		expect(screen.getByText("A股 · 沪深300")).toBeInTheDocument();
	});

	it("renders index value", () => {
		render(<MarketCard name="Test" regime="on" index="3,912.45" change={0.67} judgment="Test" />);
		expect(screen.getByText("3,912.45")).toBeInTheDocument();
	});

	it("renders change percentage", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0.67} judgment="Test" />);
		expect(screen.getByText("+0.67%")).toBeInTheDocument();
	});

	it("renders judgment text", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0.67} judgment="涨跌比偏强" />);
		expect(screen.getByText("涨跌比偏强")).toBeInTheDocument();
	});

	// ── Regime ──

	it("renders StatusBadge for regime=on", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0.67} judgment="Test" />);
		const badge = document.querySelector("[data-slot='status-badge']") as HTMLElement;
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute("data-variant", "regime-on");
	});

	it("renders StatusBadge for regime=off", () => {
		render(<MarketCard name="Test" regime="off" index="3,912" change={-1.2} judgment="Test" />);
		const badge = document.querySelector("[data-slot='status-badge']") as HTMLElement;
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute("data-variant", "regime-off");
	});

	it("renders StatusBadge for regime=mixed", () => {
		render(<MarketCard name="Test" regime="mixed" index="3,912" change={0.1} judgment="Test" />);
		const badge = document.querySelector("[data-slot='status-badge']") as HTMLElement;
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute("data-variant", "regime-mixed");
	});

	// ── Change sign ──

	it("renders positive change with + prefix", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0.67} judgment="Test" />);
		expect(screen.getByText("+0.67%")).toBeInTheDocument();
	});

	it("renders negative change with - prefix", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={-1.23} judgment="Test" />);
		expect(screen.getByText("-1.23%")).toBeInTheDocument();
	});

	// ── Structure ──

	it("renders with data-slot attribute", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0} judgment="Test" />);
		expect(document.querySelector("[data-slot='market-card']")).toBeInTheDocument();
	});

	// ── Click ──

	it("calls onClick when clicked", async () => {
		const user = userEvent.setup();
		const onClick = vi.fn();
		render(<MarketCard name="Test" regime="on" index="3,912" change={0} judgment="Test" onClick={onClick} />);
		await user.click(document.querySelector("[data-slot='market-card']") as HTMLElement);
		expect(onClick).toHaveBeenCalledTimes(1);
	});

	// ── className merging ──

	it("merges custom className", () => {
		render(<MarketCard name="Test" regime="on" index="3,912" change={0} judgment="Test" className="extra-class" />);
		const card = document.querySelector("[data-slot='market-card']") as HTMLElement;
		expect(card.classList.contains("extra-class")).toBe(true);
	});
});
