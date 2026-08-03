import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockExperimentDetail } from "@/mocks/fixtures/experiment-workbench";
import { ExperimentValidationView } from "./experiment-validation-view";

describe("ExperimentValidationView", () => {
	afterEach(() => vi.restoreAllMocks());

	it("uses the candidate and fold identities together for repeated protocol folds", () => {
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
		const fold = mockExperimentDetail.folds[0];
		expect(fold).toBeDefined();

		render(<ExperimentValidationView folds={[fold!, { ...fold!, candidate_id: "candidate-3" }]} gates={[]} />);

		expect(consoleError).not.toHaveBeenCalled();
	});
});
