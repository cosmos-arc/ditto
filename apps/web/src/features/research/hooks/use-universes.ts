import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createUniverse, deleteUniverse, fetchUniverseMembers, fetchUniverses, updateUniverse } from "../api/universes";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u;

export const universeKeys = {
	all: ["universes"] as const,
	list: () => [...universeKeys.all, "list"] as const,
	members: (universeId: string, asOf: string) => [...universeKeys.all, universeId, "members", asOf] as const,
};

export function useUniverses() {
	return useQuery({ queryKey: universeKeys.list(), queryFn: fetchUniverses });
}

export function useUniverseMembers(universeId: string, asOf: string) {
	return useQuery({
		queryKey: universeKeys.members(universeId, asOf),
		queryFn: () => fetchUniverseMembers(universeId, asOf),
		enabled: universeId.length > 0 && ISO_DATE.test(asOf),
	});
}

export function useUniverseCommands() {
	const queryClient = useQueryClient();
	const invalidate = () => queryClient.invalidateQueries({ queryKey: universeKeys.list() });
	const create = useMutation({ mutationFn: createUniverse, onSuccess: invalidate });
	const update = useMutation({
		mutationFn: ({ universeId, ...input }: Parameters<typeof updateUniverse>[1] & { readonly universeId: string }) =>
			updateUniverse(universeId, input),
		onSuccess: invalidate,
	});
	const remove = useMutation({ mutationFn: deleteUniverse, onSuccess: invalidate });
	return { create, update, remove };
}
