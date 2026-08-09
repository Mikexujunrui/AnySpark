import { create } from "zustand";
import {
  listEntities,
  listRelations,
  listEvents,
  listGraphTypes,
  type GraphEntity,
  type GraphRelation,
  type GraphEvent,
  type GraphType,
} from "../api/graph";

type Tab = "entities" | "relations" | "events";

interface GraphState {
  entities: GraphEntity[];
  relations: GraphRelation[];
  events: GraphEvent[];
  types: GraphType[];
  loading: boolean;
  tab: Tab;
  searchQuery: string;
  typeFilter: string;

  fetchAll: () => Promise<void>;
  setTab: (t: Tab) => void;
  setSearchQuery: (q: string) => void;
  setTypeFilter: (t: string) => void;
}

export const useGraphStore = create<GraphState>((set, get) => ({
  entities: [],
  relations: [],
  events: [],
  types: [],
  loading: false,
  tab: "entities",
  searchQuery: "",
  typeFilter: "",

  fetchAll: async () => {
    set({ loading: true });
    try {
      const { searchQuery, typeFilter } = get();
      const [entities, relations, events, types] = await Promise.all([
        listEntities(searchQuery || undefined, typeFilter || undefined),
        listRelations(),
        listEvents(),
        listGraphTypes(),
      ]);
      set({ entities, relations, events, types, loading: false });
    } catch (error) {
      console.error("Failed to fetch graph data:", error);
      set({ loading: false });
    }
  },

  setTab: (t) => set({ tab: t }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setTypeFilter: (t) => set({ typeFilter: t }),
}));
