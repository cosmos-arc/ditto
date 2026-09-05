import { createHash } from "node:crypto";

const ARCHIVED_PROTOTYPE_IDS = new Set(["ai-overview", "ai-copilot"]);
const UNIVERSAL_STATES = new Set(["loading", "empty", "error", "stale"]);

function sha256(content) {
	return createHash("sha256").update(content).digest("hex");
}

export function buildPrototypeSourceEvidence(inputs) {
	const normalized = [...inputs]
		.map((input) => ({ path: input.path.replaceAll("\\", "/"), content: input.content }))
		.sort((left, right) => left.path.localeCompare(right.path));
	const seen = new Set();
	const aggregate = createHash("sha256");
	const sourceInputs = normalized.map(({ path, content }) => {
		if (path === "" || path.startsWith("/") || path.split("/").includes("..")) {
			throw new Error(`Prototype source input must be workspace-relative: ${path}`);
		}
		if (seen.has(path)) throw new Error(`Duplicate prototype source input: ${path}`);
		seen.add(path);
		const inputSha256 = sha256(content);
		aggregate.update(path).update("\0").update(inputSha256).update("\0");
		return { path, sha256: inputSha256 };
	});

	if (sourceInputs.length === 0) throw new Error("Prototype source evidence cannot be empty");
	return { sourceSha256: aggregate.digest("hex"), sourceInputs };
}

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
		if (
			!artifact?.sourceSha256 ||
			!artifact?.screenshotSha256 ||
			!Array.isArray(artifact.sourceInputs) ||
			artifact.sourceInputs.length === 0
		) {
			throw new Error(`Missing frozen baseline evidence for ${page.id}`);
		}
		return {
			id: page.id,
			file: page.file,
			viewport: artifact.viewport,
			sourceSha256: artifact.sourceSha256,
			sourceInputs: artifact.sourceInputs,
			screenshotSha256: artifact.screenshotSha256,
			screenshotRef: artifact.screenshotRef,
		};
	});

	return {
		version: 2,
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
