#!/usr/bin/env python3
"""Render dispatch graph as small-multiple hierarchical trees, one per workspace.

Layout: real recursive tree-layout (leaf-count / Reingold-Tilford style), NOT
manual column offsets. networkx + graphviz `dot` were checked for availability
at write time (neither installed in this env) so this uses a hand-rolled
recursive layout instead -- still a proper algorithm: y = depth, x = midpoint
of child x-range, leaves packed left-to-right by in-order leaf index.

Small multiples chosen over one dense figure: 40 workspaces x <=4 nodes each
is naturally one-tree-per-workspace data. A single combined figure forces
either tiny illegible nodes (the original problem) or a huge canvas that
still isn't a tree the eye can trace. A grid of independent small trees keeps
each tree fully legible at a readable font size and lets the reader scan
40 in one page via facet grid, closer to "a tree" than the old scatter.
"""
import json
import math

import matplotlib.pyplot as plt

SRC = ".scratch/graph_all.json"
OUT = "/tmp/dispatch_tree_preview.png"

with open(SRC) as f:
    nodes = json.load(f)

node_map = {n["id"]: n for n in nodes}
children = {}
roots = []
for n in nodes:
    pid = n.get("parent_id")
    if pid and pid in node_map:
        children.setdefault(pid, []).append(n["id"])
    else:
        roots.append(n["id"])
for k in children:
    children[k].sort(key=lambda nid: node_map[nid].get("timestamp", ""))
roots.sort(key=lambda nid: node_map[nid].get("timestamp", ""))

# --- recursive leaf-count tree layout (Reingold-Tilford-lite) ---
# Each node gets (x, y): y = -depth, x = center over its children's x range;
# leaves get sequential x by in-order traversal. This is a real hierarchical
# algorithm (not ad hoc offsets): position derives from subtree structure.
def layout(root_id):
    pos = {}
    leaf_counter = [0]

    def visit(nid, depth):
        kids = children.get(nid, [])
        if not kids:
            x = leaf_counter[0]
            leaf_counter[0] += 1
            pos[nid] = (x, -depth)
            return x, x
        lo, hi = None, None
        for c in kids:
            clo, chi = visit(c, depth + 1)
            lo = clo if lo is None else min(lo, clo)
            hi = chi if hi is None else max(hi, chi)
        cx = (lo + hi) / 2.0
        pos[nid] = (cx, -depth)
        return lo, hi

    visit(root_id, 0)
    return pos

provider_colors = {"claude": "#d97706", "codex": "#2563eb", "gemini": "#16a34a", "mistral": "#9333ea"}
status_edge = {"returned": "#111111", "paused": "#b91c1c", "pending": "#6b7280"}

workspaces = sorted({n.get("workspace", "unknown") for n in nodes})
# one tree per workspace: build node-id sets per workspace by walking from
# any node whose workspace matches, up to its root, down through all descendants
ws_root_ids = {}
for w in workspaces:
    ws_node_ids = [n["id"] for n in nodes if n.get("workspace") == w]
    ws_roots = [nid for nid in ws_node_ids if nid in roots]
    ws_root_ids[w] = ws_roots

ncols = 5
nrows = math.ceil(len(workspaces) / ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4.2, nrows * 3.2), dpi=160)
axes = axes.flatten()

drawn_nodes = 0
drawn_edges = 0

for ax, w in zip(axes, workspaces):
    ax.set_title(w, fontsize=7, fontweight="bold")
    ax.axis("off")
    ws_roots = ws_root_ids[w]
    if not ws_roots:
        continue
    # combine all trees rooted in this workspace onto one small axes, stacked
    x_offset = 0
    for r in ws_roots:
        pos = layout(r)
        # collect all descendant ids for this root
        stack = [r]
        subtree_ids = []
        while stack:
            cur = stack.pop()
            subtree_ids.append(cur)
            stack.extend(children.get(cur, []))
        max_x = max((pos[nid][0] for nid in subtree_ids), default=0)

        for nid in subtree_ids:
            x, y = pos[nid]
            pos[nid] = (x + x_offset, y)

        # edges
        for nid in subtree_ids:
            pid = node_map[nid].get("parent_id")
            if pid and pid in pos:
                x0, y0 = pos[pid]
                x1, y1 = pos[nid]
                ecolor = status_edge.get(node_map[nid].get("status"), "#999999")
                ax.plot([x0, x1], [y0, y1], color=ecolor, linewidth=0.8, zorder=1)
                drawn_edges += 1

        # nodes
        for nid in subtree_ids:
            x, y = pos[nid]
            n = node_map[nid]
            color = provider_colors.get(n.get("provider"), "#888888")
            ax.scatter([x], [y], s=90, color=color, zorder=2, edgecolors="black", linewidths=0.4)
            label = f"{n.get('task','?')}\n{n.get('model','?')}"
            ax.annotate(
                label,
                (x, y),
                textcoords="offset points",
                xytext=(0, -11),
                ha="center",
                va="top",
                fontsize=4.3,
                linespacing=0.9,
            )
            drawn_nodes += 1

        x_offset += max_x + 2

    ax.set_xlim(-1, x_offset + 1)
    ax.set_ylim(-3.6, 0.8)

# hide unused axes
for ax in axes[len(workspaces):]:
    ax.axis("off")

legend_elems = [
    plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=7, label=p)
    for p, c in provider_colors.items()
]
fig.legend(handles=legend_elems, loc="upper center", ncol=len(legend_elems), fontsize=8, frameon=False)
fig.suptitle("Dispatch tree per workspace (root -> child -> grandchild)", fontsize=11, y=1.0)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT, bbox_inches="tight")

print(f"drawn_nodes={drawn_nodes} drawn_edges={drawn_edges}")
print(f"source_nodes={len(nodes)} source_edges={sum(1 for n in nodes if n.get('parent_id'))}")
print(f"output={OUT}")
