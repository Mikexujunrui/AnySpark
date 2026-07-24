"""Check why Firenze is a bridge character."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.graph_store import get_store

BOOK_ID = "1781418567324"
store = get_store(BOOK_ID)

# Find Firenze entity
entities = store.list_entities()
firenze = [e for e in entities if "费伦泽" in e.name or "firenze" in e.name.lower()]

if not firenze:
    for e in entities:
        if e.aliases and any("费伦泽" in a for a in e.aliases):
            firenze.append(e)

if not firenze:
    chars = [e for e in entities if e.type == "character"]
    print(f"Characters: {[c.name for c in chars]}")
    sys.exit(0)

f = firenze[0]
print(f"Entity: {f.name} (id={f.id}, type={f.type})")
print(f"Aliases: {f.aliases}")
print(f"Data: {f.data}")
print()

# Get all relations involving Firenze
rels = store.list_relations(entity_id=f.id)
print(f"Relations: {len(rels)} total")
for r in rels:
    other_id = r.to_entity if r.from_entity == f.id else r.from_entity
    other = store.get_entity(other_id)
    other_name = other.name if other else other_id
    direction = "->" if r.from_entity == f.id else "<-"
    print(f"  {f.name} {direction} [{r.type.upper()}] {other_name}")

# Check bridge character status
print()
bridges = store.find_bridge_characters()
firenze_bridge = [b for b in bridges if "费伦泽" in b.get("entity_name", "")]
if firenze_bridge:
    print(f"Bridge info: {firenze_bridge}")
else:
    top_names = [b["entity_name"] for b in bridges[:5]]
    print(f"Not in top bridge characters")
    print(f"Top bridges: {top_names}")

# Check who Firenze connects to - what communities
print()
print("=== Firenze's neighbors and their connections ===")
neighbors = store.get_neighbors(f.id, depth=1)
for n in neighbors[:10]:
    neighbor_entity = store.get_entity(n["id"])
    if neighbor_entity:
        n_rels = store.list_relations(entity_id=n["id"])
        n_char_rels = [r for r in n_rels if store.get_entity(r.to_entity if r.from_entity == n["id"] else r.from_entity)]
        print(f"  {neighbor_entity.name} ({neighbor_entity.type}) - {len(n_rels)} rels, path={n['path_types']}")
