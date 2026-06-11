import sys, json
from pathlib import Path
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from networkx.readwrite import json_graph
import networkx as nx

print("[graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)")

# 1. AST extraction of new files
inc = json.loads(Path('graphify-out/.graphify_incremental.json').read_text())
new_files = [Path(f) for cat in inc.get('new_files', {}).values() for f in cat]

result = extract(new_files, cache_root=Path('.'))
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(result, indent=2))
print(f"AST extracted {len(result['nodes'])} nodes from {len(new_files)} files")

# 2. Merge into existing graph
existing_data = json.loads(Path('graphify-out/graph.json').read_text())
G_existing = json_graph.node_link_graph(existing_data, edges='links')

new_extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
G_new = build_from_json(new_extraction)

deleted = set(inc.get('deleted_files', []))
if deleted:
    to_remove = [n for n, d in G_existing.nodes(data=True) if d.get('source_file') in deleted]
    G_existing.remove_nodes_from(to_remove)
    if to_remove:
        print(f'Pruned {len(to_remove)} ghost node(s) from {len(deleted)} deleted file(s)')

to_remove_modified = [n for n, d in G_existing.nodes(data=True) if d.get('source_file') in [str(f) for f in new_files]]
G_existing.remove_nodes_from(to_remove_modified)

G_merged = nx.compose(G_existing, G_new)

merged_out = {
    'nodes': [{'id': n, **d} for n, d in G_merged.nodes(data=True)],
    'edges': [{'source': u, 'target': v, **d} for u, v, d in G_merged.edges(data=True)],
    'input_tokens': new_extraction.get('input_tokens', 0),
    'output_tokens': new_extraction.get('output_tokens', 0),
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged_out))
print(f'[graphify update] Merged extraction written ({len(merged_out["nodes"])} nodes, {len(merged_out["edges"])} edges)')

# 3. Save manifest
from graphify.detect import save_manifest
save_manifest(inc['files'])
print('[graphify update] Manifest saved.')

