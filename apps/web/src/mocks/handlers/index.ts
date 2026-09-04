import type { RequestHandler } from "msw";
import { agentHandlers } from "./agent";
import { aiHandlers } from "./ai";
import { backtestHandlers } from "./backtest";
import { dataProductsHandlers } from "./data-products";
import { homeHandlers } from "./home";
import { instrumentsHandlers } from "./instruments";
import { intelligenceHandlers } from "./intelligence";
import { marketsHandlers } from "./markets";
import { ordersHandlers } from "./orders";
import { portfolioHandlers } from "./portfolio";
import { regimeHandlers } from "./regime";
import { researchHandlers } from "./research";
import { riskHandlers } from "./risk";
import { selectionHandlers } from "./selection";
import { strategyHandlers } from "./strategy";
import { systemHandlers } from "./system";
import { technicalAnalysisHandlers } from "./technical-analysis";
import { universeHandlers } from "./universes";

export const handlers: RequestHandler[] = [
	...agentHandlers,
	...systemHandlers,
	...homeHandlers,
	...marketsHandlers,
	...researchHandlers,
	...portfolioHandlers,
	...instrumentsHandlers,
	...backtestHandlers,
	...dataProductsHandlers,
	...strategyHandlers,
	...regimeHandlers,
	...universeHandlers,
	...intelligenceHandlers,
	...aiHandlers,
	...ordersHandlers,
	...riskHandlers,
	...selectionHandlers,
	...technicalAnalysisHandlers,
];
