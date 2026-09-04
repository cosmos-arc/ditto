import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BreachDetailContent } from "./risk-breach-detail";

describe("BreachDetailContent", () => {
	it("renders breach ID", () => {
		render(<BreachDetailContent breachId="br-001" />);
		expect(screen.getByText("ID: br-001")).toBeInTheDocument();
	});

	it("renders placeholder message", () => {
		render(<BreachDetailContent breachId="br-002" />);
		expect(screen.getByText("详细告警信息待接入 API")).toBeInTheDocument();
	});
});
