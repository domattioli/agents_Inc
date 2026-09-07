#!/usr/bin/env python3
"""CLI wrapper for phase registry resolver.

Usage:
  resolve_phases.py [--skip a,b] [--add x,y] [--json] [--explain]
  resolve_phases.py --plan-only [--add x,y] [--json]
  resolve_phases.py --list

Exit codes:
  0  success
  2  usage error
  10 unknown phase name
  11 skip/add conflict
  12 add not insertable
  13 skip required phase
  14 dependency break
"""

import sys
import json
import argparse
from phase_registry import (
    resolve,
    REGISTRY,
    UnknownPhase,
    SkipAddConflict,
    NotInsertable,
    RequiredPhaseSkip,
    DepBreak,
)


def parse_csv(csv_str):
    """Parse comma-separated values into a set, deduplicating."""
    if not csv_str:
        return set()
    return set(item.strip() for item in csv_str.split(',') if item.strip())


def main():
    parser = argparse.ArgumentParser(
        prog='resolve_phases.py',
        description='Deterministic phase resolver for speckit-pipeline',
        add_help=True
    )
    parser.add_argument('--skip', type=str, default='', help='CSV list of phases to skip')
    parser.add_argument('--add', type=str, default='', help='CSV list of phases to add')
    parser.add_argument('--allow-required-skip', action='store_true',
                        help='permit skipping required phases (specify/implement); DepBreak still guards')
    parser.add_argument('--plan-only', action='store_true',
                        help='planning-only run: skip implement (implies --allow-required-skip)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--explain', action='store_true', help='Include explanation of decisions')
    parser.add_argument('--list', action='store_true', help='List all orderable phases and exit')

    try:
        args = parser.parse_args()
    except SystemExit as e:
        # argparse calls sys.exit(2) on usage error
        if e.code != 0:
            sys.exit(2)
        raise

    # --list short-circuits everything
    if args.list:
        orderable = sorted(
            [p for p in REGISTRY.keys() if p not in ['resolve-issues', 'summary', 'illustrate']],
            key=lambda p: REGISTRY[p].order
        )
        for phase_id in orderable:
            phase = REGISTRY[phase_id]
            print(
                f"{phase.order}\t{phase_id}\t{phase.agent}\t{phase.model}\t{phase.effort}\t{phase.caveman}"
            )
        sys.exit(0)

    # Parse CSV inputs
    skip_set = parse_csv(args.skip)
    add_set = parse_csv(args.add)

    # --plan-only is sugar for "skip implement, allow the required-skip"
    force = args.allow_required_skip or args.plan_only
    if args.plan_only:
        skip_set = skip_set | {'implement'}

    # Resolve
    try:
        effective = resolve(skip_set, add_set, force=force)
    except (UnknownPhase, SkipAddConflict, NotInsertable, RequiredPhaseSkip, DepBreak) as e:
        print(str(e), file=sys.stderr)
        sys.exit(e.code)

    # Output
    if args.json:
        output = [
            {
                'phase': phase_id,
                'order': REGISTRY[phase_id].order,
                'agent': REGISTRY[phase_id].agent,
                'model': REGISTRY[phase_id].model,
                'effort': REGISTRY[phase_id].effort,
                'caveman': REGISTRY[phase_id].caveman,
            }
            for phase_id in effective
        ]
        print(json.dumps(output))
    else:
        for phase_id in effective:
            phase = REGISTRY[phase_id]
            print(
                f"{phase.order}\t{phase_id}\t{phase.agent}\t{phase.model}\t{phase.effort}\t{phase.caveman}"
            )

    sys.exit(0)


if __name__ == '__main__':
    main()
