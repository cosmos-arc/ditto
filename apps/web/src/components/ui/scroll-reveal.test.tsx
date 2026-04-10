import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { ScrollReveal } from "./scroll-reveal";

/* ── IntersectionObserver mock ── */

function mockIntersectionObserver() {
	const instances: { callback: IntersectionObserverCallback }[] = [];

	class MockIO {
		callback: IntersectionObserverCallback;
		constructor(cb: IntersectionObserverCallback) {
			this.callback = cb;
			instances.push({ callback: cb });
		}
		observe() {}
		disconnect() {}
		unobserve() {}
	}

	vi.stubGlobal("IntersectionObserver", MockIO);
	return instances;
}

describe("ScrollReveal", () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it("renders children", () => {
		mockIntersectionObserver();
		render(
			<ScrollReveal>
				<p>Hello reveal</p>
			</ScrollReveal>,
		);
		expect(screen.getByText("Hello reveal")).toBeInTheDocument();
	});

	it("has reveal-up class initially", () => {
		mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal>
				<p>Content</p>
			</ScrollReveal>,
		);
		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("reveal-up")).toBe(true);
		expect(wrapper.classList.contains("is-visible")).toBe(false);
	});

	it("gets is-visible class when IntersectionObserver triggers", () => {
		const instances = mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal>
				<p>Content</p>
			</ScrollReveal>,
		);

		// Simulate IntersectionObserver firing with isIntersecting: true
		const entry = { isIntersecting: true } as IntersectionObserverEntry;
		act(() => {
			instances[0].callback([entry], {} as IntersectionObserver);
		});

		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("is-visible")).toBe(true);
	});

	it("applies stagger-1 class when stagger={1}", () => {
		mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal stagger={1}>
				<p>Content</p>
			</ScrollReveal>,
		);
		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("stagger-1")).toBe(true);
		expect(wrapper.classList.contains("stagger-2")).toBe(false);
	});

	it("applies stagger-2 class when stagger={2}", () => {
		mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal stagger={2}>
				<p>Content</p>
			</ScrollReveal>,
		);
		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("stagger-2")).toBe(true);
		expect(wrapper.classList.contains("stagger-1")).toBe(false);
	});

	it("applies no stagger class when stagger={0} or omitted", () => {
		mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal>
				<p>Content</p>
			</ScrollReveal>,
		);
		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("stagger-1")).toBe(false);
		expect(wrapper.classList.contains("stagger-2")).toBe(false);
	});

	it("merges custom className", () => {
		mockIntersectionObserver();
		const { container } = render(
			<ScrollReveal className="my-custom-class">
				<p>Content</p>
			</ScrollReveal>,
		);
		const wrapper = container.firstElementChild as HTMLElement;
		expect(wrapper.classList.contains("my-custom-class")).toBe(true);
	});
});
