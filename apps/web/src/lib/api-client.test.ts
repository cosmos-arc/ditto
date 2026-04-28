import { describe, expect, it } from "vitest";
import { withQueryParams } from "./api-client";

describe("withQueryParams", () => {
	it("appends scalar query params and skips empty values", () => {
		expect(
			withQueryParams("/platform/pipelines", {
				page: 2,
				pageSize: 20,
				search: "",
				enabled: true,
				empty: undefined,
			}),
		).toBe("/platform/pipelines?page=2&pageSize=20&search=&enabled=true");
	});

	it("serializes structured params for GET-backed filters", () => {
		expect(
			withQueryParams("/screener/run", {
				filters: [{ field: "pe", operator: "lt", value: 20 }],
			}),
		).toBe(
			'/screener/run?filters=%5B%7B%22field%22%3A%22pe%22%2C%22operator%22%3A%22lt%22%2C%22value%22%3A20%7D%5D',
		);
	});
});
