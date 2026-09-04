const ARCHIVED_PROTOTYPE_IDS = new Set(["ai-overview", "ai-copilot"]);
const UNIVERSAL_STATES = new Set(["loading", "empty", "error", "stale"]);

export function activePrototypePages(manifest) {
	return (manifest.pages ?? [])
		.filter(
			(page) =>
				typeof page.file === "string" &&
				page.file.startsWith("page-") &&
				page.file.endsWith(".html") &&
				page.id !== "token-showcase" &&
				page.status !== "archived-specimen" &&
				!ARCHIVED_PROTOTYPE_IDS.has(page.id),
		)
		.sort((left, right) => left.id.localeCompare(right.id));
}

export function buildPrototypeBaselineRecord({
	baselineCommit,
	browserVersion,
	capturedAt,
	pages,
	artifacts,
}) {
	const entries = pages.map((page) => {
		const artifact = artifacts.get(page.id);
		if (!artifact?.sourceSha256 || !artifact?.screenshotSha256) {
			throw new Error(`Missing frozen baseline evidence for ${page.id}`);
		}
		return {
			id: page.id,
			file: page.file,
			viewport: artifact.viewport,
			sourceSha256: artifact.sourceSha256,
			screenshotSha256: artifact.screenshotSha256,
			screenshotRef: artifact.screenshotRef,
		};
	});

	return {
		version: 1,
		baselineId: `frontend-recovery-m0-${capturedAt}`,
		baselineCommit,
		capturedAt,
		browserVersion,
		prototypeCount: entries.length,
		entries,
	};
}

export function summarizePageCompletion(contract) {
	const route = contract.landing?.reactRouteStatus === "implemented" ? "verified" : "pending";
	const livePathCount =
		(contract.liveData?.readPaths?.length ?? 0) + (contract.liveData?.writePaths?.length ?? 0);
	const liveData = contract.liveData?.mockFallback === false && livePathCount > 0 ? "wired" : "pending";
	const visualParity = contract.landing?.reactParityVerified === true ? "verified" : "pending";
	const declaredStates = new Set([
		...(contract.states?.universal ?? []),
		...(contract.states?.pageSpecific ?? []),
	]);
	const testRefs = contract.landing?.reactTestRefs?.length ?? 0;
	const overlays = contract.overlays ?? [];
	const concreteOverlays = overlays.filter(
		(overlay) => overlay.reactComponent && overlay.reactComponent !== "PrototypeOnlyOverlay",
	).length;
	const statesDeclared = [...UNIVERSAL_STATES].every((state) => declaredStates.has(state));
	const workflow =
		route === "verified" &&
		liveData === "wired" &&
		visualParity === "verified" &&
		statesDeclared &&
		testRefs > 0 &&
		concreteOverlays === overlays.length
			? "verified"
			: "pending";

	return {
		route,
		liveData,
		visualParity,
		states: { declared: declaredStates.size, testRefs },
		overlays: { concrete: concreteOverlays, total: overlays.length },
		workflow,
	};
}
