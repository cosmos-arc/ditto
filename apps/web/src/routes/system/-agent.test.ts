import { describe, expect, it } from "vitest";
import { parseAgentConsoleSearch } from "./agent";

describe("parseAgentConsoleSearch", () => {
	it("keeps recoverable Agent Console context in canonical URL state", () => {
		expect(
			parseAgentConsoleSearch({
				contextId: "strategy-12@4",
				contextType: "strategy",
				offset: "40",
				objective: "核查证据链",
				selected: "run-104",
				sessionId: "session-9",
				sessionOffset: "20",
				status: "waiting_approval",
				tab: "runs",
			}),
		).toEqual({
			contextId: "strategy-12@4",
			contextType: "strategy",
			offset: 40,
			objective: "核查证据链",
			selected: "run-104",
			sessionId: "session-9",
			sessionOffset: 20,
			status: "waiting_approval",
			tab: "runs",
		});
	});

	it("fails closed to bounded defaults for invalid search", () => {
		expect(parseAgentConsoleSearch({ offset: -20, selected: 19, tab: "chat" })).toEqual({
			contextId: undefined,
			contextType: undefined,
			offset: 0,
			objective: undefined,
			selected: undefined,
			sessionId: undefined,
			sessionOffset: 0,
			status: undefined,
			tab: "runs",
		});
	});
});
