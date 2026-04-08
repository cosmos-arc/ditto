import { describe, it, expect } from "vitest";
import { dittoTheme } from "./theme";

describe("dittoTheme", () => {
	it("exports a theme object", () => {
		expect(dittoTheme).toBeDefined();
		expect(typeof dittoTheme).toBe("object");
	});

	it("has withParams method", () => {
		expect(typeof dittoTheme.withParams).toBe("function");
	});

	it("has withPart method", () => {
		expect(typeof dittoTheme.withPart).toBe("function");
	});
});
