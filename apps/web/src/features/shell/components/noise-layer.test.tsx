import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { NoiseLayer } from "./noise-layer";

describe("NoiseLayer", () => {
	it("renders a decorative overlay with pointer-events-none", () => {
		const { container } = render(<NoiseLayer />);
		const overlay = container.firstChild as HTMLElement;
		expect(overlay.className).toContain("pointer-events-none");
	});

	it("has absolute positioning with inset-0 and z-0", () => {
		const { container } = render(<NoiseLayer />);
		const overlay = container.firstChild as HTMLElement;
		expect(overlay.className).toContain("absolute");
		expect(overlay.className).toContain("inset-0");
		expect(overlay.className).toContain("z-0");
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
		const topBar = container.querySelector('[data-testid="noise-top-light"]');
		expect(topBar).toBeInTheDocument();
	});

	it("does not render a right ambient light bar (moved to Rail)", () => {
		const { container } = render(<NoiseLayer />);
		const rightBar = container.querySelector('[data-testid="noise-right-light"]');
		expect(rightBar).not.toBeInTheDocument();
	});

	it("has correct structure with noise SVG and top light bar only", () => {
		const { container } = render(<NoiseLayer />);
		const svg = container.querySelector("svg");
		const topBar = container.querySelector('[data-testid="noise-top-light"]');

		expect(svg).toBeInTheDocument();
		expect(topBar).toBeInTheDocument();
	});

	it("top ambient light bar uses brand color via CSS variable", () => {
		const { container } = render(<NoiseLayer />);
		const topBar = container.querySelector('[data-testid="noise-top-light"]') as HTMLElement;

		expect(topBar.style.backgroundImage).toContain("--color-accent");
	});
});
