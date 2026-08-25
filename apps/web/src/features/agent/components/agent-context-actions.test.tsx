import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentContextActions } from "./agent-context-actions";

describe("AgentContextActions", () => {
	it("passes only stable context identity and the explicit objective", () => {
		render(
			<AgentContextActions
				contextType="experiment-candidate"
				contextId="exp-1042:candidate-2"
				evidenceObjective="复核候选证据与排除原因"
				authorObjective="提出结构化实验变更草案"
			/>,
		);

		const evidence = screen.getByRole("link", { name: "请求证据分析" });
		const evidenceUrl = new URL(evidence.getAttribute("href") ?? "", "http://ditto.local");
		expect(Object.fromEntries(evidenceUrl.searchParams)).toEqual({
			contextId: "exp-1042:candidate-2",
			contextType: "experiment-candidate",
			objective: "复核候选证据与排除原因",
			tab: "runs",
		});

		const author = screen.getByRole("link", { name: "请求 Author 草案" });
		expect(new URL(author.getAttribute("href") ?? "", "http://ditto.local").searchParams.get("objective")).toBe(
			"提出结构化实验变更草案",
		);
	});
});
