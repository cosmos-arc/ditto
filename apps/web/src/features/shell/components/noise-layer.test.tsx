import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { NoiseLayer } from "./noise-layer";

describe("NoiseLayer", () => {
	it("renders a decorative overlay with pointer-events-none", () => {
		const { container } = render(<NoiseLayer />);
		const overlay = container.firstChild as HTMLElement;
		expect(overlay.className).toContain("pointer-events-none");
	});

	it("has absolute positioning with inset-0 and z-50", () => {
		const { container } = render(<NoiseLayer />);
		const overlay = container.firstChild as HTMLElement;
		expect(overlay.className).toContain("absolute");
		expect(overlay.className).toContain("inset-0");
		expect(overlay.className).toContain("z-50");
	});

	it("contains an SVG element for the noise filter", () => {
		const { container } = render(<NoiseLayer />);
		const svg = container.querySelector("svg");
		expect(svg).toBeInTheDocument();
	});

	it("SVG uses feTurbulence filter for noise generation", () => {
		const { container } = render(<NoiseLayer />);
		const turbulence = container.querySelector("feTurbulence");
		expect(turbulence).toBeInTheDocument();
		expect(turbulence?.getAttribute("type")).toBe("fractalNoise");
	});

	it("SVG noise overlay has very low opacity", () => {
		const { container } = render(<NoiseLayer />);
		const svg = container.querySelector("svg");
		// The SVG should have a very low opacity for subtle noise
		expect(svg?.getAttribute("opacity")).toBe("0.018");
	});

	it("renders a top ambient light bar", () => {
		const { container } = render(<NoiseLayer />);
		// Find the top gradient bar — a div with a gradient background
		const bars = container.querySelectorAll("[data-testid]");
		const topBar = container.querySelector('[data-testid="noise-top-light"]');
		expect(topBar).toBeInTheDocument();
	});

	it("renders a right ambient light bar", () => {
		const { container } = render(<NoiseLayer />);
		const rightBar = container.querySelector('[data-testid="noise-right-light"]');
		expect(rightBar).toBeInTheDocument();
	});

	it("has correct structure with noise SVG and two light bars", () => {
		const { container } = render(<NoiseLayer />);
		const svg = container.querySelector("svg");
		const topBar = container.querySelector('[data-testid="noise-top-light"]');
		const rightBar = container.querySelector('[data-testid="noise-right-light"]');

		expect(svg).toBeInTheDocument();
		expect(topBar).toBeInTheDocument();
		expect(rightBar).toBeInTheDocument();
	});

	it("ambient light bars use brand color via CSS variable", () => {
		const { container } = render(<NoiseLayer />);
		const topBar = container.querySelector('[data-testid="noise-top-light"]') as HTMLElement;
		const rightBar = container.querySelector('[data-testid="noise-right-light"]') as HTMLElement;

		// Both bars should reference the brand color in their gradient
		expect(topBar.className).toContain("color-accent");
		expect(rightBar.className).toContain("color-accent");
	});
});
