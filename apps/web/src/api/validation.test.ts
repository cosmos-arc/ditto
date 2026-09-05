import { describe, expect, it } from "vitest";
import { arrayValue, integerValue, RuntimeValidationError, recordValue } from "./validation";

describe("runtime boundary validation", () => {
	it.each([null, [], "payload"])("rejects non-record payload %#", (payload) => {
		expect(() => recordValue(payload, "boundary")).toThrow(RuntimeValidationError);
	});

	it.each([1.5, Number.MAX_SAFE_INTEGER + 1, -1])("rejects unsafe or below-minimum integer %#", (value) => {
		expect(() => integerValue({ count: value }, "count", "boundary", 0)).toThrow(/integer >= 0/u);
	});

	it("rejects non-array collection fields instead of accepting iterable lookalikes", () => {
		expect(() => arrayValue({ items: { 0: "value" } }, "items", "boundary")).toThrow(/expected an array/u);
	});
});
