import type { RequestHandler } from "msw";
import { aiHandlers } from "./ai";
import { backtestHandlers } from "./backtest";
import { homeHandlers } from "./home";
import { instrumentsHandlers } from "./instruments";
import { intelligenceHandlers } from "./intelligence";
import { marketsHandlers } from "./markets";
import { ordersHandlers } from "./orders";
import { platformHandlers } from "./platform";
import { regimeHandlers } from "./regime";
import { researchHandlers } from "./research";
import { riskHandlers } from "./risk";
import { strategyHandlers } from "./strategy";
import { tradingHandlers } from "./trading";

export const handlers: RequestHandler[] = [
	...platformHandlers,
	...homeHandlers,
	...marketsHandlers,
	...researchHandlers,
	...tradingHandlers,
	...instrumentsHandlers,
	...backtestHandlers,
	...strategyHandlers,
	...regimeHandlers,
	...intelligenceHandlers,
	...aiHandlers,
	...ordersHandlers,
	...riskHandlers,
];
