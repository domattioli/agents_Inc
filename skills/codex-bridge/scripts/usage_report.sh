#!/usr/bin/env bash
set -euo pipefail

# Create temp file for Python script
tmpdir=$(mktemp -d)
trap "rm -rf $tmpdir" EXIT

cat > "$tmpdir/usage_report.py" << 'PYTHON_EOF'
#!/usr/bin/env python3
"""
Read-only token usage report across Claude & delegated backends.
Groups by (backend, model), sums usage counters separately.
Pricing from reference/prices.json. Output: plain text table (default) or JSON.
"""
import json
import glob
import os
import sys
from datetime import datetime
from collections import defaultdict
import argparse

def parse_args():
    p = argparse.ArgumentParser(description='Usage report')
    p.add_argument('--since', help='Start date YYYY-MM-DD')
    p.add_argument('--until', help='End date YYYY-MM-DD (exclusive)')
    p.add_argument('--days', type=int, help='Last N days')
    p.add_argument('--json', action='store_true', help='JSON output')
    p.add_argument('--prices', help='Path to prices.json')
    return p.parse_args()

def load_prices(path=None):
    """Load pricing data. Returns (models_dict, subscriptions_dict)."""
    if not path:
        # Try to find prices.json in the project structure
        # First try from cwd (project root)
        candidates = [
            './skills/codex-bridge/reference/prices.json',
            os.path.join(os.getcwd(), 'skills/codex-bridge/reference/prices.json'),
            os.path.expanduser('~/.claude/../../Projects/claude-codex/skills/codex-bridge/reference/prices.json'),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                path = candidate
                break

        if not path:
            return {}, {}

    if not os.path.exists(path):
        return {}, {}

    try:
        with open(path) as f:
            data = json.load(f)
        return data.get('models', {}), data.get('subscriptions', {})
    except:
        return {}, {}

def load_claude_transcripts(since_date=None, until_date=None, until_days_ago=None):
    """Load Claude transcripts from ~/.claude/projects/**/*.jsonl. Yields (ts, model, usage_dict, message_id)."""
    pattern = os.path.expanduser('~/.claude/projects/**/*.jsonl')

    for filepath in glob.glob(pattern, recursive=True):
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if 'message' not in obj:
                            continue
                        msg = obj['message']
                        if 'usage' not in msg:
                            continue

                        ts_str = obj.get('timestamp', '')
                        model = msg.get('model')
                        usage = msg.get('usage', {})
                        message_id = msg.get('id')

                        # Skip synthetic or empty models
                        if not model or model == '<synthetic>' or not usage:
                            continue

                        # Parse timestamp
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        except:
                            ts = None

                        # Apply date filters
                        if since_date and ts and ts.date() < since_date:
                            continue
                        if until_date and ts and ts.date() >= until_date:
                            continue
                        if until_days_ago is not None and ts:
                            import datetime as dt_module
                            cutoff = (datetime.now().replace(tzinfo=ts.tzinfo) if ts.tzinfo else datetime.now())
                            cutoff = cutoff - dt_module.timedelta(days=until_days_ago)
                            if ts < cutoff:
                                continue

                        yield (ts, model, usage, message_id)
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        except (IOError, OSError):
            continue

def load_delegated_usage(since_date=None, until_date=None, until_days_ago=None):
    """Load delegated usage from ~/.codex-bridge/usage.jsonl. Yields (ts, backend, model, input_tokens, output_tokens, reasoning_tokens)."""
    path = os.path.expanduser('~/.codex-bridge/usage.jsonl')
    if not os.path.exists(path):
        return

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ts_str = obj.get('ts')
                    backend = obj.get('backend')
                    model = obj.get('model')
                    input_tokens = obj.get('input_tokens', 0)
                    output_tokens = obj.get('output_tokens', 0)
                    reasoning_tokens = obj.get('reasoning_tokens', 0)

                    if not ts_str or not backend:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    except:
                        ts = None

                    if since_date and ts and ts.date() < since_date:
                        continue
                    if until_date and ts and ts.date() >= until_date:
                        continue
                    if until_days_ago is not None and ts:
                        import datetime as dt_module
                        cutoff = (datetime.now().replace(tzinfo=ts.tzinfo) if ts.tzinfo else datetime.now()) - dt_module.timedelta(days=until_days_ago)
                        if ts < cutoff:
                            continue

                    yield (ts, backend, model, input_tokens, output_tokens, reasoning_tokens)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
    except (IOError, OSError):
        pass

def aggregate_usage(transcripts, delegated, prices_models):
    """Group by (backend, model), sum counters. Returns (by_model dict, first_ts, last_ts, record_count, unreadable_count, skipped_dupe_count)."""
    by_model = defaultdict(lambda: {
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_read_input_tokens': 0,
        'cache_creation_input_tokens': 0,
        'reasoning_tokens': 0
    })

    first_ts = None
    last_ts = None
    count_records = 0
    count_unreadable = 0
    count_dupe = 0
    seen_message_ids = set()

    # Process Claude transcripts
    for ts, model, usage, message_id in transcripts:
        try:
            # Deduplicate by message_id
            if message_id and message_id in seen_message_ids:
                count_dupe += 1
                continue
            if message_id:
                seen_message_ids.add(message_id)

            key = ('claude', model)
            by_model[key]['input_tokens'] += usage.get('input_tokens', 0)
            by_model[key]['output_tokens'] += usage.get('output_tokens', 0)
            by_model[key]['cache_read_input_tokens'] += usage.get('cache_read_input_tokens', 0)
            by_model[key]['cache_creation_input_tokens'] += usage.get('cache_creation_input_tokens', 0)
            count_records += 1
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
        except:
            count_unreadable += 1

    # Process delegated usage
    for ts, backend, model, input_tokens, output_tokens, reasoning_tokens in delegated:
        try:
            key = (backend, model)
            by_model[key]['input_tokens'] += input_tokens
            by_model[key]['output_tokens'] += output_tokens
            by_model[key]['reasoning_tokens'] += reasoning_tokens
            count_records += 1
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
        except:
            count_unreadable += 1

    return by_model, first_ts, last_ts, count_records, count_unreadable, count_dupe

def lookup_price(model_name, prices_models):
    """Look up price for a model name with fallback for date-suffixed versions.
    First tries exact match, then strips trailing -YYYYMMDD and retries."""
    if not model_name or not prices_models:
        return None

    # Try exact match first
    if model_name in prices_models:
        return prices_models[model_name]

    # Try stripping date suffix (e.g., claude-haiku-4-5-20251001 -> claude-haiku-4-5)
    import re
    match = re.search(r'^(.+)-(\d{8})$', model_name)
    if match:
        base_model = match.group(1)
        if base_model in prices_models:
            return prices_models[base_model]

    return None

def compute_cost(usage_dict, model_prices):
    """Compute USD cost. Returns total in USD or None if unpriced.
    Missing keys are treated as 0.0 (free). Explicit None rate is unpriceable."""
    input_tok = usage_dict.get('input_tokens', 0)
    output_tok = usage_dict.get('output_tokens', 0)
    cache_read_tok = usage_dict.get('cache_read_input_tokens', 0)
    cache_write_tok = usage_dict.get('cache_creation_input_tokens', 0)
    reasoning_tok = usage_dict.get('reasoning_tokens', 0)

    if model_prices is None:
        return None

    cost = 0.0

    # Input: if key missing and have tokens, treat as free (0.0)
    if 'input' in model_prices:
        rate = model_prices['input']
        if rate is not None:
            cost += (input_tok / 1_000_000) * rate
        elif input_tok > 0:
            return None
    # else: key missing, assume free (0.0)

    # Output
    if 'output' in model_prices:
        rate = model_prices['output']
        if rate is not None:
            cost += (output_tok / 1_000_000) * rate
        elif output_tok > 0:
            return None
    # else: key missing, assume free (0.0)

    # Reasoning: if key missing and have tokens, treat as free (0.0)
    if 'reasoning' in model_prices:
        rate = model_prices['reasoning']
        if rate is not None:
            cost += (reasoning_tok / 1_000_000) * rate
        # else: rate is None, don't fail; assume free tier (e.g., gemini)
    # else: key missing, assume free (0.0)

    # Cache read: if key missing and have tokens, treat as free (0.0)
    if 'cache_read' in model_prices:
        rate = model_prices['cache_read']
        if rate is not None:
            cost += (cache_read_tok / 1_000_000) * rate
        # else: rate is None, don't fail; assume free
    # else: key missing, assume free (0.0)

    # Cache write: if key missing and have tokens, treat as free (0.0)
    if 'cache_write' in model_prices:
        rate = model_prices['cache_write']
        if rate is not None:
            cost += (cache_write_tok / 1_000_000) * rate
        # else: rate is None, don't fail; assume free
    # else: key missing, assume free (0.0)

    return cost

def format_table(by_model, prices_models, subscriptions, first_ts, last_ts, count_records, count_files, count_dupe):
    """Format as fixed-width table. Deterministic sort: cost desc, then model asc."""
    rows = []
    count_unpriced = 0
    count_priced = 0
    total_cost = 0.0

    for (backend, model), usage in sorted(by_model.items()):
        # Skip synthetic models and empty strings (but allow None for backends like codex)
        if model == '<synthetic>' or model == '':
            continue

        price = lookup_price(model, prices_models)
        cost = compute_cost(usage, price)
        if cost is None:
            cost = 0.0
            cost_str = '?'
            count_unpriced += 1
        else:
            cost_str = f'${cost:.2f}'
            total_cost += cost
            count_priced += 1

        row = {
            'backend': backend,
            'model': model,
            'input_tokens': usage['input_tokens'],
            'output_tokens': usage['output_tokens'],
            'cache_read': usage['cache_read_input_tokens'],
            'cache_write': usage['cache_creation_input_tokens'],
            'reasoning_tokens': usage['reasoning_tokens'],
            'cost': cost,
            'cost_str': cost_str
        }
        rows.append(row)

    # Sort deterministically: cost desc, model asc (None sorts first)
    rows.sort(key=lambda r: (-r['cost'], r['model'] or ''))

    # Compute column widths from data
    if rows:
        max_backend = max(len(r['backend']) for r in rows)
        max_model = max(len(r['model'] or '') for r in rows)
        max_input = max(len(f"{r['input_tokens']:,}") for r in rows)
        max_output = max(len(f"{r['output_tokens']:,}") for r in rows)
        max_reason = max(len(f"{r['reasoning_tokens']:,}") for r in rows)
        max_cache_rd = max(len(f"{r['cache_read']:,}") for r in rows)
        max_cache_wr = max(len(f"{r['cache_write']:,}") for r in rows)
        max_cost = max(len(r['cost_str']) for r in rows)
    else:
        max_backend = 7
        max_model = 16
        max_input = 9
        max_output = 7
        max_reason = 9
        max_cache_rd = 9
        max_cache_wr = 9
        max_cost = 7

    # Format period string
    if first_ts and last_ts:
        period_str = f"{first_ts.isoformat()} .. {last_ts.isoformat()}"
    else:
        period_str = "all records"

    lines = []
    lines.append('Usage report')
    lines.append(f'period: {period_str}')
    lines.append(f'records: {count_records}   files scanned: {count_files}')
    lines.append('')

    # Build header
    header1 = (
        f"{'backend':<{max_backend}}  {'model':<{max_model}}  "
        f"{'input':>{max_input}}  {'output':>{max_output}}  "
        f"{'reason':>{max_reason}}  {'cache_rd':>{max_cache_rd}}  {'cache_wr':>{max_cache_wr}}  {'est $':>{max_cost}}"
    )
    header2 = (
        f"{'-' * max_backend}  {'-' * max_model}  "
        f"{'-' * max_input}  {'-' * max_output}  "
        f"{'-' * max_reason}  {'-' * max_cache_rd}  {'-' * max_cache_wr}  {'-' * max_cost}"
    )
    lines.append(header1)
    lines.append(header2)

    for row in rows:
        line = (
            f"{row['backend']:<{max_backend}}  {(row['model'] or ''):<{max_model}}  "
            f"{row['input_tokens']:>{max_input},}  {row['output_tokens']:>{max_output},}  "
            f"{row['reasoning_tokens']:>{max_reason},}  {row['cache_read']:>{max_cache_rd},}  {row['cache_write']:>{max_cache_wr},}  {row['cost_str']:>{max_cost}}"
        )
        lines.append(line)

    lines.append(header2)
    lines.append(f'TOTAL est: ${total_cost:.2f}  (models priced: {count_priced}, unpriced: {count_unpriced})')
    if count_dupe > 0:
        lines.append(f'note: {count_dupe} duplicate messages skipped (same message.id)')
    lines.append('')
    lines.append('Subscription comparison')

    for sub_name, sub_info in sorted(subscriptions.items()):
        # Skip metadata keys
        if sub_name.startswith('_'):
            continue
        # Skip if not a dict
        if not isinstance(sub_info, dict):
            continue

        monthly = sub_info.get('monthly_usd', 0)
        covers = sub_info.get('covers', [])
        covers_str = ', '.join(covers) if covers else 'none'

        # Compute metered equiv for this subscription: sum costs from rows that match its covers
        metered_sub = 0.0
        matched_rows = 0
        for row in rows:
            backend = row['backend']
            model = row['model']
            cost = row['cost']

            # Check if this row matches any of the covers
            for cover in covers:
                matched = False
                if cover.endswith('*'):
                    # Prefix match: 'gemini-*' matches backend 'gemini' or model starting with 'gemini'
                    prefix = cover[:-1]
                    if backend.startswith(prefix) or model.startswith(prefix):
                        matched = True
                elif cover == backend:
                    # Backend match: 'codex' matches backend 'codex'
                    matched = True
                elif cover == model:
                    # Model name match: 'gemini-3.8-flash' matches model 'gemini-3.8-flash'
                    matched = True

                if matched:
                    metered_sub += cost
                    matched_rows += 1
                    break  # Don't double-count if multiple covers match

        # Determine verdict
        if matched_rows == 0:
            verdict = 'no recorded use'
        elif metered_sub == 0:
            verdict = 'KEEP - free tier'
        elif metered_sub > monthly:
            verdict = 'KEEP'
        else:
            verdict = f'REVIEW - costs ${monthly:.2f} vs ${metered_sub:.2f} metered'

        lines.append(f"  {sub_name:<20} ${monthly:.2f}/mo   covers: {covers_str}   metered equiv: ${metered_sub:.2f}   {verdict}")

    # Add claude API-metered line: sum all claude backend costs
    claude_cost = sum(r['cost'] for r in rows if r['backend'] == 'claude')
    lines.append(f"  {'claude (API-metered)':<20} (no subscription)   metered equiv: ${claude_cost:.2f}")

    return '\n'.join(lines)

def format_json(by_model, prices_models, first_ts, last_ts):
    """Format as JSON. Deterministic: sort_keys=True."""
    result = {
        'period_start': first_ts.isoformat() if first_ts else None,
        'period_end': last_ts.isoformat() if last_ts else None,
        'usage_by_model': {}
    }

    for (backend, model), usage in sorted(by_model.items()):
        result['usage_by_model'][f'{backend}:{model}'] = {
            'input_tokens': usage['input_tokens'],
            'output_tokens': usage['output_tokens'],
            'reasoning_tokens': usage['reasoning_tokens'],
            'cache_read_input_tokens': usage['cache_read_input_tokens'],
            'cache_creation_input_tokens': usage['cache_creation_input_tokens']
        }

    return json.dumps(result, sort_keys=True, indent=2)

def main():
    args = parse_args()

    # Parse date filters
    since_date = None
    until_date = None
    until_days_ago = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, '%Y-%m-%d').date()
        except ValueError:
            print(f'Error: invalid --since date {args.since}', file=sys.stderr)
            sys.exit(1)

    if args.until:
        try:
            until_date = datetime.strptime(args.until, '%Y-%m-%d').date()
        except ValueError:
            print(f'Error: invalid --until date {args.until}', file=sys.stderr)
            sys.exit(1)

    if args.days is not None:
        until_days_ago = args.days

    # Load prices
    prices_models, subscriptions = load_prices(args.prices)

    # Load usage data
    transcripts_list = list(load_claude_transcripts(since_date, until_date, until_days_ago))
    delegated_list = list(load_delegated_usage(since_date, until_date, until_days_ago))

    # Count unique files scanned (from transcript file paths)
    files_scanned = len(set(
        os.path.expanduser('~/.claude/projects/**/*.jsonl')
        for _ in transcripts_list
    ))
    # Simpler: just count the number of jsonl files we actually read from
    pattern = os.path.expanduser('~/.claude/projects/**/*.jsonl')
    files_scanned = len(glob.glob(pattern, recursive=True))

    # Aggregate
    by_model, first_ts, last_ts, count_records, count_unreadable, count_dupe = aggregate_usage(
        transcripts_list, delegated_list, prices_models
    )

    # Output
    if not by_model:
        print('no usage records found')
        sys.exit(0)

    if args.json:
        print(format_json(by_model, prices_models, first_ts, last_ts))
    else:
        print(format_table(by_model, prices_models, subscriptions, first_ts, last_ts, count_records, files_scanned, count_dupe))
        if count_unreadable > 0:
            print(f'note: {count_unreadable} records unreadable; period may be incomplete')

if __name__ == '__main__':
    main()
PYTHON_EOF

python3 "$tmpdir/usage_report.py" "$@"
