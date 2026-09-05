import type {
	AgentFinding,
	GetAgentFindingsResponse,
	GetHomeAgentFindingsResponse,
	GetOrdersSummaryResponse,
	GetResearchPulseResponse,
	GetSignalsQueueResponse,
	HomeAgentFinding,
	ResearchPulseResponse,
} from "@/types";

type AssertExported = [
	GetOrdersSummaryResponse,
	GetSignalsQueueResponse,
	ResearchPulseResponse,
	GetResearchPulseResponse,
	HomeAgentFinding,
	GetHomeAgentFindingsResponse,
	AgentFinding,
	GetAgentFindingsResponse,
];

it("exports canonical API response types without domain collisions", () => {
	const exportedTypesAreAvailable: AssertExported | null = null;
	expect(exportedTypesAreAvailable).toBeNull();
	expect(true satisfies boolean).toBe(true);
});
