import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountIdentityStrip } from "./account-identity-strip";

describe("AccountIdentityStrip", () => {
	it.each([
		["model", "MODEL 目标组合", "版本化目标，不接受成交或现金流水"],
		["paper", "PAPER 模拟账户", "由 Ditto 模拟撮合，不连接券商下单"],
		["manual", "MANUAL 手工实际账户", "只记录用户确认的实际账户事实"],
	] as const)("keeps %s identity explicit", (kind, label, boundary) => {
		render(<AccountIdentityStrip kind={kind} accountId={`${kind}-a`} accountName="核心组合" />);

		expect(screen.getByText(label)).toBeInTheDocument();
		expect(screen.getByText(boundary)).toBeInTheDocument();
		expect(screen.getByText(`${kind}-a`)).toBeInTheDocument();
	});
});
