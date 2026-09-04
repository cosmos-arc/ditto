import { ApiError } from "@/lib/api-client";

export type MutationFailureKind = "none" | "conflict" | "unknown" | "definite";

export function classifyMutationFailure(error: unknown): MutationFailureKind {
	if (!error) return "none";
	if (!(error instanceof ApiError)) return "unknown";
	if (error.status === 409) return "conflict";
	if (error.status >= 500 && error.status < 600) return "unknown";
	return "definite";
}
