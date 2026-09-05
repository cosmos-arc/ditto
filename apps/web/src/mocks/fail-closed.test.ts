import { expect, it } from "vitest";

it("fails an unhandled mock API request without reaching a real API", async () => {
	const response = await fetch("/api/v1/no-such-operation");
	expect(response.status).toBe(501);
	await expect(response.json()).resolves.toMatchObject({ error_code: "MOCK_API_UNHANDLED" });
});
