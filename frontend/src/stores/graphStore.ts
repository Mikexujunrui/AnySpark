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
    try {
      const entity = await createEntity(req);
      set({ entities: [...get().entities, entity] });
    } catch (e) {
      console.error("addEntity failed:", e);
      throw e;
    }
  },
  editEntity: async (id, req) => {
    try {
      const updated = await updateEntity(id, req);
      set({ entities: get().entities.map((e) => (e.id === id ? updated : e)) });
    } catch (e) {
      console.error("editEntity failed:", e);
      throw e;
    }
  },
  removeEntity: async (id) => {
    try {
      await deleteEntity(id);
      set({ entities: get().entities.filter((e) => e.id !== id) });
    } catch (e) {
      console.error("removeEntity failed:", e);
      throw e;
    }
  },
  
  /* Relation */
  addRelation: async (req) => {
    try {
      const rel = await createRelation(req);
      set({ relations: [...get().relations, rel] });
    } catch (e) {
      console.error("addRelation failed:", e);
      throw e;
    }
  },
  editRelation: async (id, req) => {
    try {
      const updated = await updateRelation(id, req);
      set({ relations: get().relations.map((r) => (r.id === id ? updated : r)) });
    } catch (e) {
      console.error("editRelation failed:", e);
      throw e;
    }
  },
  removeRelation: async (id) => {
    try {
      await deleteRelation(id);
      set({ relations: get().relations.filter((r) => r.id !== id) });
    } catch (e) {
      console.error("removeRelation failed:", e);
      throw e;
    }
  },
  
  /* Event */
  addEvent: async (req) => {
    try {
      const evt = await createEvent(req);
      set({ events: [...get().events, evt] });
    } catch (e) {
      console.error("addEvent failed:", e);
      throw e;
    }
  },
  editEvent: async (id, req) => {
    try {
      const updated = await updateEvent(id, req);
      set({ events: get().events.map((e) => (e.id === id ? updated : e)) });
    } catch (e) {
      console.error("editEvent failed:", e);
      throw e;
    }
  },
  removeEvent: async (id) => {
    try {
      await deleteEvent(id);
      set({ events: get().events.filter((e) => (e.id !== id)) });
    } catch (e) {
      console.error("removeEvent failed:", e);
      throw e;
    }
  },
}));
