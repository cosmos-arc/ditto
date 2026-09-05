import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { materializeCohortCompatibilityPolicy } from "./src/api/build-metadata.ts";

const SUPPORTED_API_CONTRACT_VERSION = "v1";

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), "");
	const apiTarget = env["VITE_DEV_API_TARGET"] ?? "http://localhost:8000";
	const repositoryRoot = path.resolve(import.meta.dirname, "../..");
	const contractBytes = readFileSync(path.join(repositoryRoot, "contracts/openapi/v1.json"));
	const contractSha256 = createHash("sha256").update(contractBytes).digest("hex");
	const policyPath = path.join(repositoryRoot, "contracts/cohorts/compatibility-policy.json");
	const policyBytes = readFileSync(policyPath);
	const policySha256 = createHash("sha256").update(policyBytes).digest("hex");
	const policyDigest = readFileSync(path.join(repositoryRoot, "contracts/cohorts/compatibility-policy.sha256"), "utf8");
	const expectedPolicyDigest = `${policySha256}  compatibility-policy.json\n`;
	if (policyDigest !== expectedPolicyDigest) {
		throw new Error("compatibility policy SHA-256 sidecar is malformed or stale");
	}
	const policySource: unknown = JSON.parse(policyBytes.toString("utf8"));
	const declaredContractSha256 = env["DITTO_API_CONTRACT_SHA256"]?.trim();
	if (declaredContractSha256 && declaredContractSha256 !== contractSha256) {
		throw new Error(
			`DITTO_API_CONTRACT_SHA256 does not match contracts/openapi/v1.json: declared=${declaredContractSha256}, actual=${contractSha256}`,
		);
	}
	const workspace = JSON.parse(readFileSync(path.join(repositoryRoot, "package.json"), "utf8")) as {
		readonly version?: unknown;
	};
	if (typeof workspace.version !== "string" || workspace.version.length === 0) {
		throw new Error("workspace package.json must declare a product version");
	}
	const gitSha =
		env["DITTO_GIT_SHA"]?.trim() ||
		execFileSync("git", ["rev-parse", "HEAD"], { cwd: repositoryRoot, encoding: "utf8" }).trim();
	if (!/^[0-9a-f]{40}$/u.test(gitSha)) throw new Error("Web build Git SHA must be a full lowercase commit hash");
	const apiContractVersion = env["DITTO_API_CONTRACT_VERSION"]?.trim() || SUPPORTED_API_CONTRACT_VERSION;
	if (apiContractVersion !== SUPPORTED_API_CONTRACT_VERSION) {
		throw new Error(`Web API contract version must equal ${SUPPORTED_API_CONTRACT_VERSION}`);
	}
	const currentIdentity = {
		productVersion: env["DITTO_PRODUCT_VERSION"]?.trim() || workspace.version,
		gitSha,
		apiContractVersion: SUPPORTED_API_CONTRACT_VERSION,
		apiContractSha256: contractSha256,
	} as const;
	const buildMetadata = {
		...currentIdentity,
		compatibilityPolicy: materializeCohortCompatibilityPolicy(policySource, policySha256, currentIdentity),
	};
	const buildMetadataArtifact = {
		apiContractSha256: buildMetadata.apiContractSha256,
		apiContractVersion: buildMetadata.apiContractVersion,
		compatibilityPolicy: buildMetadata.compatibilityPolicy,
		gitSha: buildMetadata.gitSha,
		productVersion: buildMetadata.productVersion,
		schema: "ditto.web-build-metadata",
		schemaVersion: 1,
	} as const;

	return {
		define: {
			__DITTO_WEB_BUILD_METADATA__: JSON.stringify(buildMetadata),
		},
		plugins: [
			{
				name: "ditto-web-build-metadata-artifact",
				apply: "build",
				generateBundle() {
					this.emitFile({
						type: "asset",
						fileName: "ditto-build-metadata.json",
						source: `${JSON.stringify(buildMetadataArtifact, null, 2)}\n`,
					});
				},
			},
			TanStackRouterVite({ autoCodeSplitting: true, quoteStyle: "double" }),
			react(),
			tailwindcss(),
		],
		resolve: {
			alias: {
				"@": path.resolve(import.meta.dirname, "./src"),
			},
		},
		server: {
			proxy: {
				"/api": {
					target: apiTarget,
					changeOrigin: true,
				},
			},
		},
		build: {
			manifest: true,
		},
	};
});
