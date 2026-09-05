import { useLocation } from "@tanstack/react-router";
import { DOMAINS, type DomainId } from "@/features/navigation";

function isDomainActive(domainId: DomainId, pathname: string): boolean {
	const domain = DOMAINS.find((d) => d.id === domainId);
	if (!domain) return false;
	if (domainId === "home") return pathname === "/";
	return pathname.startsWith(domain.path);
}

export function useActiveDomain(): DomainId {
	const { pathname } = useLocation();
	const domain = DOMAINS.find((d) => isDomainActive(d.id, pathname));
	return domain?.id ?? "home";
}
