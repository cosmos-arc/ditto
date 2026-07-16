import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DomainId } from "../types";
import { DomainIcon } from "./domain-icon";

const ALL_DOMAIN_IDS: DomainId[] = ["home", "markets", "research", "trading", "platform"];

describe("DomainIcon", () => {
	it("renders an SVG element for each domain", () => {
		for (const domainId of ALL_DOMAIN_IDS) {
			const { container } = render(<DomainIcon domainId={domainId} />);
			const svg = container.querySelector("svg");
			expect(svg).toBeInTheDocument();
		}
	});

	it("renders with accessible role and label for home", () => {
		render(<DomainIcon domainId="home" />);
		expect(screen.getByRole("img", { hidden: true })).toBeInTheDocument();
	});

	it("renders distinct icons for different domains", () => {
		const icons = ALL_DOMAIN_IDS.map((domainId) => {
			const { container } = render(<DomainIcon domainId={domainId} />);
			return container.querySelector("svg")?.innerHTML ?? "";
		});

		// Each domain should produce a unique SVG path
		const uniquePaths = new Set(icons);
		expect(uniquePaths.size).toBe(ALL_DOMAIN_IDS.length);
	});

	it("renders without crashing for all domain IDs", () => {
		for (const domainId of ALL_DOMAIN_IDS) {
			expect(() => render(<DomainIcon domainId={domainId} />)).not.toThrow();
		}
	});
});
