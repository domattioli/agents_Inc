import sys
import json
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Load data
with open('.scratch/graph_all.json', 'r') as f:
    nodes = json.load(f)

n_nodes = len(nodes)
node_map = {node['id']: node for node in nodes}

# Filter valid edges (parent exists in node_map)
edges = []
for node in nodes:
    pid = node.get('parent_id')
    if pid and pid in node_map:
        edges.append((pid, node['id'], node.get('edge_type', '')))

n_edges = len(edges)

# Group nodes by workspace
workspaces = sorted(list(set(node.get('workspace', 'unknown') for node in nodes)))

# Separate workspaces into columns: 'off' prefix vs 'enforce' (or others)
off_ws = [w for w in workspaces if w.startswith('off')]
enforce_ws = [w for w in workspaces if w.startswith('enforce')]
other_ws = [w for w in workspaces if w not in off_ws and w not in enforce_ws]

# We will create a grid: 2 columns. Left column: 'off', Right column: 'enforce' (plus others if any)
# Rows will correspond to max index between columns to keep alignment
max_rows = max(len(off_ws), len(enforce_ws) + len(other_ws))
if max_rows == 0:
    max_rows = 1

fig, ax = plt.subplots(figsize=(14, 22), dpi=150)

# Colors
provider_colors = {
    'claude': 'orange',
    'codex': 'green'
}
default_provider_color = 'gray'

status_edge_colors = {
    'returned': 'black',
    'paused': 'red'
}
default_status_color = 'blue'

# Layout configuration
# Columns: x_base for col 0 (off) = 0, x_base for col 1 (enforce) = 5
col_x_offsets = {0: 0.0, 1: 9.0}

# Map workspace to (col, row)
ws_layout = {}
r = 0
for w in off_ws:
    ws_layout[w] = (0, r)
    r += 1

r = 0
for w in enforce_ws:
    ws_layout[w] = (1, r)
    r += 1

for w in other_ws:
    ws_layout[w] = (1, r)
    r += 1

# Compute node positions (x, y)
# For each workspace, root node at x=0, children at x=1, y = row index
# To handle multiple roots or trees per workspace simply:
node_pos = {}

for ws, (col, row_idx) in ws_layout.items():
    ws_nodes = [n for n in nodes if n.get('workspace') == ws]
    
    # Find roots (parent_id is None or not in this workspace)
    ws_node_ids = {n['id'] for n in ws_nodes}
    roots = [n for n in ws_nodes if not n.get('parent_id') or n.get('parent_id') not in ws_node_ids]
    
    # Simple deterministic layout per workspace:
    # Row index in global plot Y coordinate: we invert row_idx so row 0 is at the top
    base_y = -row_idx * 3.0
    
    # Assign positions
    # If multiple roots, spread them vertically a bit or just stack
    root_y = base_y
    for i, root in enumerate(roots):
        rid = root['id']
        rx = col_x_offsets[col] + 0.0
        ry = root_y - (i * 0.5)
        node_pos[rid] = (rx, ry)
        
        # Children (depth 1)
        children = [n for n in ws_nodes if n.get('parent_id') == rid]
        for c_idx, child in enumerate(children):
            cid = child['id']
            cx = col_x_offsets[col] + 1.5
            cy = ry - (c_idx - len(children)/2.0 + 0.5) * 0.4
            node_pos[cid] = (cx, cy)
            
            # Grandchildren just in case
            g_children = [n for n in ws_nodes if n.get('parent_id') == cid]
            for gc_idx, gchild in enumerate(g_children):
                gcid = gchild['id']
                gcx = col_x_offsets[col] + 3.0
                gcy = cy - (gc_idx - len(g_children)/2.0 + 0.5) * 0.3
                node_pos[gcid] = (gcx, gcy)

# Fallback for any unpositioned nodes
for node in nodes:
    nid = node['id']
    if nid not in node_pos:
        node_pos[nid] = (0.0, 0.0)

# Draw workspace labels on the left of each row
for ws, (col, row_idx) in ws_layout.items():
    base_y = -row_idx * 3.0
    label_x = col_x_offsets[col] - 1.2
    ax.text(label_x, base_y, ws, fontweight='bold', fontsize=9, ha='right', va='center',
            bbox=dict(boxstyle='round,pad=0.2', fc='lightyellow', ec='gray', alpha=0.5))

# Draw edges
for pid, cid, etype in edges:
    if pid in node_pos and cid in node_pos:
        px, py = node_pos[pid]
        cx, cy = node_pos[cid]
        ax.annotate("",
                    xy=(cx, cy), xycoords='data',
                    xytext=(px, py), textcoords='data',
                    arrowprops=dict(arrowstyle="->", color="gray", lw=1, shrinkA=10, shrinkB=10,
                                    connectionstyle="arc3,rad=0.0"))
        if etype:
            ax.text((px + cx) / 2.0, (py + cy) / 2.0 + 0.1, etype, fontsize=6, color='dimgray', ha='center', va='bottom')

# Draw nodes
for node in nodes:
    nid = node['id']
    if nid not in node_pos:
        continue
    x, y = node_pos[nid]
    
    provider = node.get('provider', '')
    status = node.get('status', '')
    task = node.get('task', 'task')
    model = node.get('model', 'model')
    
    facecolor = provider_colors.get(provider, default_provider_color)
    edgecolor = status_edge_colors.get(status, default_status_color)
    
    # Draw node circle marker
    ax.plot(x, y, marker='o', markersize=14, markerfacecolor=facecolor, markeredgecolor=edgecolor, markeredgewidth=2, zorder=3)
    
    # Node text
    label_text = f"{task}/{model}"
    ax.text(x, y - 0.35, label_text, fontsize=5, ha='center', va='top', wrap=True, clip_on=True)

# Set limits and formatting
pass
ax.axis('off')

# Title
ax.set_title(f"workerbees dispatch graph — T15 bench 2026-09-06, {n_nodes} nodes, {n_edges} edges", fontsize=12, fontweight='bold', pad=20)

# Legend
legend_elements = [
    Line2D([0], [0], marker='o', color='w', label='Claude (Provider)', markerfacecolor='orange', markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Codex (Provider)', markerfacecolor='green', markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Returned (Status)', markerfacecolor='gray', markeredgecolor='black', markeredgewidth=2, markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Paused (Status)', markerfacecolor='gray', markeredgecolor='red', markeredgewidth=2, markersize=10),
]
ax.legend(handles=legend_elements, loc='upper right', fontsize=8, framealpha=0.9)

plt.tight_layout()

# Save output
if len(sys.argv) > 1:
    out_path = sys.argv[1]
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
else:
    plt.savefig('dispatch_graph.png', dpi=150, bbox_inches='tight')
