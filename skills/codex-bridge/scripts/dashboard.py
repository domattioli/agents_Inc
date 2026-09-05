#!/usr/bin/env python3
"""
Generate a self-contained HTML dashboard from usage.db and prices.json.
No CDN dependencies. Inline CSS + SVG charts + JSON data.
Theme-aware: light + dark modes with toggle.

CLI: python3 dashboard.py [--out PATH] [--db PATH] [--days N]
"""
import sqlite3
import json
import os
import sys
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

PALETTE_LIGHT = {
    'blue': '#2a78d6',
    'orange': '#eb6834',
    'aqua': '#1baf7a',
    'yellow': '#eda100',
    'surface': '#fcfcfb',
    'text': '#1a1a19',
    'grid': '#e0e0de',
}

PALETTE_DARK = {
    'blue': '#3987e5',
    'orange': '#d95926',
    'aqua': '#199e70',
    'yellow': '#c98500',
    'surface': '#1a1a19',
    'text': '#e8e8e6',
    'grid': '#3a3a39',
}

def parse_args():
    p = argparse.ArgumentParser(description='Generate usage dashboard')
    p.add_argument('--out', default='demo/usage-dashboard.html', help='Output HTML path')
    p.add_argument('--db', help='Custom DB path')
    p.add_argument('--days', type=int, help='Limit to last N days')
    return p.parse_args()

def get_db_path(custom_path=None):
    if custom_path:
        return custom_path
    db_dir = Path.home() / '.codex-bridge'
    return str(db_dir / 'usage.db')

def load_prices():
    """Load prices.json, return models dict."""
    candidates = [
        './skills/codex-bridge/reference/prices.json',
        os.path.join(os.getcwd(), 'skills/codex-bridge/reference/prices.json'),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    return json.load(f).get('models', {})
            except:
                pass
    return {}

def load_usage(db_path, limit_days=None):
    """Load usage data, return (rows, first_day, last_day)."""
    conn = sqlite3.connect(db_path)
    query = 'SELECT ts, day, backend, model, input_tokens, output_tokens, cache_read, cache_write, reasoning FROM usage ORDER BY ts'
    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        return [], None, None

    # Apply day limit
    if limit_days:
        cutoff = (datetime.now() - timedelta(days=limit_days)).date()
        rows = [r for r in rows if r[1] >= cutoff.isoformat()]

    if not rows:
        return [], None, None

    first_day = rows[0][1]
    last_day = rows[-1][1]
    return rows, first_day, last_day

def lookup_price(model_name, prices_models):
    """Exact match, then strip -YYYYMMDD suffix."""
    if not model_name or not prices_models:
        return None
    if model_name in prices_models:
        return prices_models[model_name]
    match = re.search(r'^(.+)-(\d{8})$', model_name)
    if match:
        base = match.group(1)
        if base in prices_models:
            return prices_models[base]
    return None

def compute_cost(usage_dict, model_prices):
    """Compute cost. Returns None if unpriced, float otherwise (including 0.0)."""
    if model_prices is None:
        return None

    input_tok = usage_dict.get('input_tokens', 0)
    output_tok = usage_dict.get('output_tokens', 0)
    cache_read_tok = usage_dict.get('cache_read', 0)
    cache_write_tok = usage_dict.get('cache_write', 0)
    reasoning_tok = usage_dict.get('reasoning', 0)

    cost = 0.0

    # Input: if key missing, treat as 0.0; if 0.0 explicitly, that's a price of 0.0
    if 'input' in model_prices:
        rate = model_prices['input']
        if rate is not None:
            cost += (input_tok / 1_000_000) * rate
        elif input_tok > 0:
            return None
    elif input_tok > 0:
        return None

    # Output
    if 'output' in model_prices:
        rate = model_prices['output']
        if rate is not None:
            cost += (output_tok / 1_000_000) * rate
        elif output_tok > 0:
            return None
    elif output_tok > 0:
        return None

    # Reasoning: if missing key and have tokens, treat as 0.0 (free tier)
    if 'reasoning' in model_prices:
        rate = model_prices['reasoning']
        if rate is not None:
            cost += (reasoning_tok / 1_000_000) * rate
        # If rate is None but tokens > 0, don't fail; assume free

    # Cache read: if missing key and have tokens, treat as 0.0
    if 'cache_read' in model_prices:
        rate = model_prices['cache_read']
        if rate is not None:
            cost += (cache_read_tok / 1_000_000) * rate

    # Cache write: if missing key and have tokens, treat as 0.0
    if 'cache_write' in model_prices:
        rate = model_prices['cache_write']
        if rate is not None:
            cost += (cache_write_tok / 1_000_000) * rate

    return cost

def aggregate_by_model(rows, prices_models):
    """Group by (backend, model), compute stats. Return sorted list of (backend, model, stats)."""
    by_model = {}
    for ts_str, day, backend, model, input_tok, output_tok, cache_read, cache_write, reasoning in rows:
        key = (backend, model)
        if key not in by_model:
            by_model[key] = {
                'input_tokens': 0,
                'output_tokens': 0,
                'cache_read': 0,
                'cache_write': 0,
                'reasoning': 0,
            }
        by_model[key]['input_tokens'] += input_tok
        by_model[key]['output_tokens'] += output_tok
        by_model[key]['cache_read'] += cache_read
        by_model[key]['cache_write'] += cache_write
        by_model[key]['reasoning'] += reasoning

    # Compute costs and build result
    result = []
    for (backend, model), usage in by_model.items():
        price = lookup_price(model, prices_models)
        cost = compute_cost(usage, price)
        result.append({
            'backend': backend,
            'model': model,
            'usage': usage,
            'cost': cost if cost is not None else 0.0,
            'is_priced': cost is not None,
        })

    # Sort by cost desc, model asc
    result.sort(key=lambda x: (-x['cost'], x['model'] or ''))
    return result

def aggregate_by_day_backend(rows):
    """Group by (day, backend), sum tokens. Return dict[day][backend] = {input, output, ...}."""
    by_day = {}
    for ts_str, day, backend, model, input_tok, output_tok, cache_read, cache_write, reasoning in rows:
        if day not in by_day:
            by_day[day] = {}
        if backend not in by_day[day]:
            by_day[day][backend] = {
                'input_tokens': 0,
                'output_tokens': 0,
                'cache_read': 0,
                'cache_write': 0,
                'reasoning': 0,
            }
        by_day[day][backend]['input_tokens'] += input_tok
        by_day[day][backend]['output_tokens'] += output_tok
        by_day[day][backend]['cache_read'] += cache_read
        by_day[day][backend]['cache_write'] += cache_write
        by_day[day][backend]['reasoning'] += reasoning
    return by_day

def svg_bar_chart_cost(models_data):
    """Horizontal bar chart: cost by model. Returns SVG string."""
    if not models_data:
        return '<svg></svg>'

    w, h = 800, 300
    margin = {'left': 250, 'right': 100, 'top': 30, 'bottom': 30}
    inner_w = w - margin['left'] - margin['right']
    inner_h = h - margin['top'] - margin['bottom']

    max_cost = max((m['cost'] for m in models_data), default=1)
    if max_cost == 0:
        max_cost = 1

    bar_height = inner_h / len(models_data) if models_data else 20
    colors = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']

    svg_lines = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" class="chart">',
        '<defs><style>',
        '.chart-text { font-family: system-ui; font-size: 12px; }',
        '.chart-label-left { text-anchor: end; }',
        '.chart-label-right { text-anchor: start; }',
        '</style></defs>',
        f'<rect x="{margin["left"]}" y="{margin["top"]}" width="{inner_w}" height="{inner_h}" fill="none" stroke="var(--chart-grid)" stroke-width="0.5"/>',
    ]

    for i, model_info in enumerate(models_data):
        y_pos = margin['top'] + i * bar_height
        bar_width = (model_info['cost'] / max_cost) * inner_w
        color = colors[i % len(colors)]

        if model_info['is_priced']:
            bar_fill = color
        else:
            bar_fill = 'none'
            bar_stroke = 'var(--chart-grid)'

        if model_info['is_priced']:
            svg_lines.append(
                f'<rect x="{margin["left"]}" y="{y_pos}" width="{bar_width}" height="{bar_height - 2}" fill="{bar_fill}" rx="2"/>'
            )
        else:
            svg_lines.append(
                f'<rect x="{margin["left"]}" y="{y_pos}" width="{bar_width}" height="{bar_height - 2}" fill="none" stroke="{bar_stroke}" stroke-width="1" rx="2"/>'
            )

        # Model label (left)
        label = model_info['model'] or f"{model_info['backend']}"
        svg_lines.append(
            f'<text x="{margin["left"] - 5}" y="{y_pos + bar_height/2 + 4}" class="chart-text chart-label-left" fill="var(--chart-text)">{label}</text>'
        )

        # Cost label (right)
        if model_info['is_priced']:
            cost_str = f"${model_info['cost']:.2f}"
        else:
            cost_str = "n/a"
        svg_lines.append(
            f'<text x="{margin["left"] + bar_width + 5}" y="{y_pos + bar_height/2 + 4}" class="chart-text chart-label-right" fill="var(--chart-text)">{cost_str}</text>'
        )

    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)

def svg_daily_tokens(by_day_backend):
    """Stacked area chart: daily tokens by backend."""
    if not by_day_backend:
        return '<svg></svg>'

    days = sorted(by_day_backend.keys())
    backends = sorted(set(b for day_data in by_day_backend.values() for b in day_data.keys()))

    w, h = 800, 300
    margin = {'left': 60, 'right': 20, 'top': 30, 'bottom': 60}
    inner_w = w - margin['left'] - margin['right']
    inner_h = h - margin['top'] - margin['bottom']

    # Compute max total tokens per day
    daily_totals = []
    for day in days:
        total = sum(by_day_backend[day].get(b, {}).get('input_tokens', 0) +
                   by_day_backend[day].get(b, {}).get('output_tokens', 0)
                   for b in backends)
        daily_totals.append(total)

    max_tokens = max(daily_totals, default=1)
    if max_tokens == 0:
        max_tokens = 1

    colors_by_backend = {'claude': '#2a78d6', 'codex': '#eb6834', 'gemini': '#1baf7a'}

    svg_lines = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" class="chart">',
        f'<rect x="{margin["left"]}" y="{margin["top"]}" width="{inner_w}" height="{inner_h}" fill="none" stroke="var(--chart-grid)" stroke-width="0.5"/>',
    ]

    x_step = inner_w / len(days) if days else 1
    y_scale = inner_h / max_tokens

    for i, day in enumerate(days):
        x_pos = margin['left'] + i * x_step
        # Date label
        svg_lines.append(
            f'<text x="{x_pos}" y="{h - 10}" class="chart-text" font-size="11" text-anchor="middle" fill="var(--chart-text)">{day}</text>'
        )

    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)

def generate_html(models_data, by_day_backend, first_day, last_day, total_rows, prices_models, rows):
    """Generate complete HTML dashboard."""

    # Stat tiles
    total_cost = sum(m['cost'] for m in models_data)
    total_tokens = sum(r[4] + r[5] + r[6] + r[7] + r[8] for r in rows)

    html_lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<title>Usage Dashboard</title>',
        '<style>',
        ':root {',
        '  --bg-surface: #fcfcfb;',
        '  --bg-alt: #f5f5f4;',
        '  --text: #1a1a19;',
        '  --text-dim: #7a7a78;',
        '  --border: #e0e0de;',
        '  --chart-grid: #e0e0de;',
        '  --chart-text: #1a1a19;',
        '  --blue: #2a78d6;',
        '  --orange: #eb6834;',
        '  --aqua: #1baf7a;',
        '  --yellow: #eda100;',
        '}',
        '@media (prefers-color-scheme: dark) {',
        '  :root:not([data-theme="light"]) {',
        '    --bg-surface: #1a1a19;',
        '    --bg-alt: #2a2a29;',
        '    --text: #e8e8e6;',
        '    --text-dim: #a0a09e;',
        '    --border: #3a3a39;',
        '    --chart-grid: #3a3a39;',
        '    --chart-text: #e8e8e6;',
        '    --blue: #3987e5;',
        '    --orange: #d95926;',
        '    --aqua: #199e70;',
        '    --yellow: #c98500;',
        '  }',
        '}',
        ':root[data-theme="dark"] {',
        '  --bg-surface: #1a1a19;',
        '  --bg-alt: #2a2a29;',
        '  --text: #e8e8e6;',
        '  --text-dim: #a0a09e;',
        '  --border: #3a3a39;',
        '  --chart-grid: #3a3a39;',
        '  --chart-text: #e8e8e6;',
        '  --blue: #3987e5;',
        '  --orange: #d95926;',
        '  --aqua: #199e70;',
        '  --yellow: #c98500;',
        '}',
        'body {',
        '  margin: 0;',
        '  padding: 20px;',
        '  background: var(--bg-surface);',
        '  color: var(--text);',
        '  font-family: system-ui, -apple-system, sans-serif;',
        '  font-size: 14px;',
        '  line-height: 1.5;',
        '}',
        'h1, h2 { margin-top: 0; }',
        '.toggle-theme {',
        '  position: fixed; top: 20px; right: 20px;',
        '  padding: 8px 12px; border: 1px solid var(--border);',
        '  background: var(--bg-alt); color: var(--text);',
        '  cursor: pointer; border-radius: 4px; font-size: 12px;',
        '}',
        '.stat-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin: 20px 0; }',
        '.tile { background: var(--bg-alt); padding: 16px; border-radius: 8px; border: 1px solid var(--border); }',
        '.tile-value { font-size: 24px; font-weight: bold; color: var(--text); }',
        '.tile-label { font-size: 12px; color: var(--text-dim); margin-top: 4px; }',
        '.section { margin: 40px 0; }',
        '.chart { max-width: 100%; height: auto; }',
        'table { width: 100%; border-collapse: collapse; margin: 20px 0; }',
        'th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }',
        'th { background: var(--bg-alt); font-weight: bold; }',
        'tr:hover { background: var(--bg-alt); }',
        '</style>',
        '</head>',
        '<body>',
        '<button class="toggle-theme" onclick="toggleTheme()">🌙</button>',
        '<h1>Usage Dashboard</h1>',
    ]

    # Stat tiles
    html_lines.extend([
        '<div class="stat-tiles">',
        f'<div class="tile"><div class="tile-value">${total_cost:.2f}</div><div class="tile-label">Est. Cost</div></div>',
        f'<div class="tile"><div class="tile-value">{total_tokens:,}</div><div class="tile-label">Total Tokens</div></div>',
        f'<div class="tile"><div class="tile-value">{first_day} .. {last_day}</div><div class="tile-label">Period</div></div>',
        f'<div class="tile"><div class="tile-value">{total_rows}</div><div class="tile-label">Records</div></div>',
        '</div>',
    ])

    # Cost by model section
    html_lines.extend([
        '<div class="section">',
        '<h2>Cost by Model</h2>',
        svg_bar_chart_cost(models_data),
        '</div>',
    ])

    # Daily tokens section
    html_lines.extend([
        '<div class="section">',
        '<h2>Daily Tokens</h2>',
        svg_daily_tokens(by_day_backend),
        '</div>',
    ])

    # Token composition section
    html_lines.extend([
        '<div class="section">',
        '<h2>Token Composition by Model</h2>',
    ])

    # Table: Token breakdown
    html_lines.extend([
        '<table>',
        '<thead><tr><th>Backend</th><th>Model</th><th>Input</th><th>Output</th><th>Reasoning</th><th>Cache Read</th><th>Cache Write</th><th>Est. Cost</th></tr></thead>',
        '<tbody>',
    ])
    for model_info in models_data:
        cost_str = f"${model_info['cost']:.2f}" if model_info['is_priced'] else "n/a"
        usage = model_info['usage']
        html_lines.append(
            f'<tr><td>{model_info["backend"]}</td><td>{model_info["model"] or ""}</td>'
            f'<td>{usage["input_tokens"]:,}</td><td>{usage["output_tokens"]:,}</td>'
            f'<td>{usage["reasoning"]:,}</td><td>{usage["cache_read"]:,}</td>'
            f'<td>{usage["cache_write"]:,}</td><td>{cost_str}</td></tr>'
        )
    html_lines.extend([
        '</tbody>',
        '</table>',
        '</div>',
    ])

    # Footer + data + script
    html_lines.extend([
        '<script>',
        'function toggleTheme() {',
        '  const root = document.documentElement;',
        '  const current = root.getAttribute("data-theme");',
        '  const next = current === "dark" ? "light" : "dark";',
        '  root.setAttribute("data-theme", next);',
        '  localStorage.setItem("theme", next);',
        '}',
        'window.addEventListener("load", () => {',
        '  const saved = localStorage.getItem("theme");',
        '  if (saved) document.documentElement.setAttribute("data-theme", saved);',
        '});',
        '</script>',
        '</body>',
        '</html>',
    ])

    return '\n'.join(html_lines)

def main():
    args = parse_args()

    # Load data
    db_path = get_db_path(args.db)
    if not os.path.exists(db_path):
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    rows, first_day, last_day = load_usage(db_path, args.days)
    if not rows:
        print("Error: no usage data found", file=sys.stderr)
        sys.exit(1)

    prices_models = load_prices()
    models_data = aggregate_by_model(rows, prices_models)
    by_day_backend = aggregate_by_day_backend(rows)

    # Generate HTML
    html = generate_html(models_data, by_day_backend, first_day, last_day, len(rows), prices_models, rows)

    # Write output
    out_path = args.out
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, 'w') as f:
        f.write(html)

    print(f"Dashboard written to {out_path}")

if __name__ == '__main__':
    main()
