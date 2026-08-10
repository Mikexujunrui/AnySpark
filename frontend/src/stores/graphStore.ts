import { create } from "zustand";
import {
  listEntities,
  listRelations,
  listEvents,
  listGraphTypes,
  createEntity,
  updateEntity,
  deleteEntity,
  createRelation,
  updateRelation,
  deleteRelation,
  createEvent,
  updateEvent,
  deleteEvent,
  type GraphEntity,
  type GraphRelation,
  type GraphEvent,
  type GraphType,
  type CreateEntityRequest,
  type UpdateEntityRequest,
  type CreateRelationRequest,
  type UpdateRelationRequest,
  type CreateEventRequest,
  type UpdateEventRequest,
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

  /* Entity CRUD */
  addEntity: (req: CreateEntityRequest) => Promise<void>;
  editEntity: (id: string, req: UpdateEntityRequest) => Promise<void>;
  removeEntity: (id: string) => Promise<void>;

  /* Relation CRUD */
  addRelation: (req: CreateRelationRequest) => Promise<void>;
  editRelation: (id: string, req: UpdateRelationRequest) => Promise<void>;
  removeRelation: (id: string) => Promise<void>;

  /* Event CRUD */
  addEvent: (req: CreateEventRequest) => Promise<void>;
  editEvent: (id: string, req: UpdateEventRequest) => Promise<void>;
  removeEvent: (id: string) => Promise<void>;
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

  /* Entity */
  addEntity: async (req) => {
    const entity = await createEntity(req);
    set({ entities: [...get().entities, entity] });
  },
  editEntity: async (id, req) => {
    const updated = await updateEntity(id, req);
    set({ entities: get().entities.map((e) => (e.id === id ? updated : e)) });
  },
  removeEntity: async (id) => {
    await deleteEntity(id);
    set({ entities: get().entities.filter((e) => e.id !== id) });
  },

  /* Relation */
  addRelation: async (req) => {
    const rel = await createRelation(req);
    set({ relations: [...get().relations, rel] });
  },
  editRelation: async (id, req) => {
    const updated = await updateRelation(id, req);
    set({ relations: get().relations.map((r) => (r.id === id ? updated : r)) });
  },
  removeRelation: async (id) => {
    await deleteRelation(id);
    set({ relations: get().relations.filter((r) => r.id !== id) });
  },

  /* Event */
  addEvent: async (req) => {
    const evt = await createEvent(req);
    set({ events: [...get().events, evt] });
  },
  editEvent: async (id, req) => {
    const updated = await updateEvent(id, req);
    set({ events: get().events.map((e) => (e.id === id ? updated : e)) });
  },
  removeEvent: async (id) => {
    await deleteEvent(id);
    set({ events: get().events.filter((e) => e.id !== id) });
  },
}));
