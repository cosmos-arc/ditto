import { describe, expect, it } from "vitest";
import { auditRouteCoverage, deriveExpectedProductRoutes } from "./audit-route-coverage-core.mjs";

describe("route coverage audit", () => {
	it("derives product routes from page contracts and explicit React-only manifest entries", () => {
		const routes = deriveExpectedProductRoutes(
			[
				{ id: "home", route: "/" },
				{ id: "alpha-explorer", route: "/research/alpha" },
			],
			{
				reactOnlyRoutes: [{ route: "/system/data-products", featureModule: "src/features/data-products" }],
			},
		);

		expect(routes).toEqual(["/", "/research/alpha", "/system/data-products"]);
	});

	it("reports alpha as missing instead of allowing a hard-coded IA list to hide it", () => {
		const result = auditRouteCoverage({
			expectedRoutes: ["/", "/research/alpha"],
			actualRoutes: ["/", "/research/node-descriptors", "/showcase"],
			allowedNonProductRoutes: ["/research/node-descriptors", "/showcase"],
		});

		expect(result).toEqual({ missingRoutes: ["/research/alpha"], unexpectedRoutes: [] });
	});
});
