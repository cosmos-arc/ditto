import { useQuery } from "@tanstack/react-query";
import { fetchFactorCatalog } from "../api/factor-catalog";

export function useFactorCatalog() {
	return useQuery({
		queryKey: ["research", "factor-catalog"],
		queryFn: fetchFactorCatalog,
	});
}
