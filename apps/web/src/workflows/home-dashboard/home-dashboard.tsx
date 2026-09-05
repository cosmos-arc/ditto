import { HomePage as HomeView } from "@/features/home";
import { fetchCurrentMarketContext } from "@/workflows/market-context";

/** App composition for the Home view's cross-feature MarketContext dependency. */
export function HomePage() {
	return <HomeView loadMarketContext={fetchCurrentMarketContext} />;
}
