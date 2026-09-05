export function deriveExpectedProductRoutes(contracts, editionManifest) {
	const routes = [
		...contracts.map((contract) => contract.route),
		...(editionManifest.reactOnlyRoutes ?? []).map((entry) => entry.route),
	];
	return [...new Set(routes.map(normalizeRoute))].sort();
}

export function auditRouteCoverage({ expectedRoutes, actualRoutes, allowedNonProductRoutes = [] }) {
	const expected = new Set(expectedRoutes.map(normalizeRoute));
	const actual = new Set(actualRoutes.map(normalizeRoute));
	const allowed = new Set(allowedNonProductRoutes.map(normalizeRoute));

	return {
		missingRoutes: [...expected].filter((route) => !actual.has(route)).sort(),
		unexpectedRoutes: [...actual].filter((route) => !expected.has(route) && !allowed.has(route)).sort(),
	};
}

export function normalizeRoute(route) {
	const normalized = route.replace(/\/+$/, "");
	return normalized === "" ? "/" : normalized;
}
