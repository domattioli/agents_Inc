#!/usr/bin/env python3
"""Phase registry and resolver for speckit-pipeline.

Pure function, zero I/O. Encodes all 11 orderable phases with their dependencies,
agent targets, model assignments, and effort estimates.
"""

from collections import namedtuple

# Phase registry entry: all metadata about a phase
Phase = namedtuple(
    'Phase',
    ['order', 'default', 'insertable', 'required', 'interactive', 'deps', 'agent', 'model', 'effort', 'caveman', 'skill_dir']
)

# Complete phase registry: id -> Phase object
REGISTRY = {
    'constitution': Phase(
        order=5,
        default=False,
        insertable=True,
        required=False,
        interactive='if-principles-unspecified',
        deps=[],
        agent='main session',
        model='session',
        effort='high',
        caveman='none',
        skill_dir='speckit-constitution'
    ),
    'specify': Phase(
        order=10,
        default=True,
        insertable=False,
        required=True,
        interactive='no',
        deps=[],
        agent='main session',
        model='session',
        effort='high',
        caveman='none',
        skill_dir='speckit-specify'
    ),
    'clarify': Phase(
        order=20,
        default=True,
        insertable=False,
        required=False,
        interactive='yes (human gate)',
        deps=['specify'],
        agent='main session',
        model='session',
        effort='session',
        caveman='light',
        skill_dir='speckit-clarify'
    ),
    'plan': Phase(
        order=30,
        default=True,
        insertable=False,
        required=False,
        interactive='no',
        deps=['specify'],
        agent='Plan',
        model='opus/sonnet',
        effort='high',
        caveman='dispatch max · plan.md none',
        skill_dir='speckit-plan'
    ),
    'tasks': Phase(
        order=40,
        default=True,
        insertable=False,
        required=False,
        interactive='no',
        deps=['plan'],
        agent='general-purpose',
        model='sonnet',
        effort='medium',
        caveman='dispatch max · tasks.md none',
        skill_dir='speckit-tasks'
    ),
    'tasks-to-issues': Phase(
        order=42,
        default=False,
        insertable=True,
        required=False,
        interactive='no',
        deps=['tasks'],
        agent='general-purpose',
        model='haiku',
        effort='low',
        caveman='dispatch max · issue light',
        skill_dir='speckit-taskstoissues'
    ),
    'split': Phase(
        order=44,
        default=False,
        insertable=True,
        required=False,
        interactive='no',
        deps=['specify'],
        agent='general-purpose',
        model='haiku',
        effort='low',
        caveman='dispatch max · issue light',
        skill_dir='speckit-split'
    ),
    'checklist': Phase(
        order=50,
        default=True,
        insertable=False,
        required=False,
        interactive='no',
        deps=['specify'],
        agent='general-purpose',
        model='haiku',
        effort='low',
        caveman='dispatch max · checklist none',
        skill_dir='speckit-checklist'
    ),
    'analyze': Phase(
        order=60,
        default=True,
        insertable=False,
        required=False,
        interactive='no',
        deps=['specify', 'plan', 'tasks'],
        agent='adversarial-reviewer',
        model='sonnet/opus',
        effort='high',
        caveman='dispatch max · report max',
        skill_dir='speckit-analyze'
    ),
    'implement': Phase(
        order=70,
        default=True,
        insertable=False,
        required=True,
        interactive='no',
        deps=['plan', 'tasks'],
        agent='cavecrew-builder (preset)',
        model='haiku',
        effort='medium (esc. high if broad)',
        caveman='dispatch max · code normal',
        skill_dir='speckit-implement'
    ),
    'commit': Phase(
        order=80,
        default=False,
        insertable=True,
        required=False,
        interactive='no',
        deps=['implement'],
        agent='main session',
        model='session',
        effort='low',
        caveman='caveman-commit',
        skill_dir='speckit-git-commit'
    ),
}

# Non-orderable phases (excluded from skip/add)
REGISTRY['resolve-issues'] = Phase(
    order=None,
    default=None,
    insertable=None,
    required=None,
    interactive=None,
    deps=[],
    agent='main / cavecrew-builder',
    model='sonnet',
    effort='medium',
    caveman='dispatch max · edits none',
    skill_dir=None
)
REGISTRY['summary'] = Phase(
    order=None,
    default=None,
    insertable=None,
    required=None,
    interactive=None,
    deps=[],
    agent='main (nested-notes)',
    model='session',
    effort='low',
    caveman='light',
    skill_dir=None
)
REGISTRY['illustrate'] = Phase(
    order=None,
    default=None,
    insertable=None,
    required=None,
    interactive=None,
    deps=[],
    agent='main (accelerate)',
    model='session',
    effort='low',
    caveman='n/a',
    skill_dir=None
)

# Orderable set (default + insertable, excludes resolve-issues/summary/illustrate)
DEFAULTS = {'specify', 'clarify', 'plan', 'tasks', 'checklist', 'analyze', 'implement'}
INSERTABLE = {'constitution', 'tasks-to-issues', 'split', 'commit'}
REQUIRED = {'specify', 'implement'}

# Exception classes with structured data and exit codes
class UnknownPhase(Exception):
    """Exit code 10: unrecognized phase name(s)."""
    code = 10

    def __init__(self, names, valid):
        self.names = names
        self.valid = valid
        super().__init__(
            f"Unknown phase name(s): {', '.join(names)}. Valid: {', '.join(valid)}"
        )


class SkipAddConflict(Exception):
    """Exit code 11: phase appears in both --skip and --add."""
    code = 11

    def __init__(self, names):
        self.names = names
        super().__init__(
            f"Phase(s) appear in both --skip and --add: {', '.join(names)}"
        )


class NotInsertable(Exception):
    """Exit code 12: attempted to add a non-insertable phase."""
    code = 12

    def __init__(self, names, insertable_set):
        self.names = names
        self.insertable_set = insertable_set
        super().__init__(
            f"Cannot add non-insertable phase(s): {', '.join(names)}. "
            f"Insertable phases: {', '.join(sorted(insertable_set))}"
        )


class RequiredPhaseSkip(Exception):
    """Exit code 13: attempted to skip a required phase."""
    code = 13

    def __init__(self, names):
        self.names = names
        super().__init__(
            f"Cannot skip required phase(s): {', '.join(names)}"
        )


class DepBreak(Exception):
    """Exit code 14: unmet dependencies in the effective set."""
    code = 14

    def __init__(self, violations):
        self.violations = violations  # list of (phase, missing_dep) tuples
        super().__init__(
            "Dependency broken. Phase(s) missing required input:\n" +
            "\n".join(
                f"  {phase} requires {dep}"
                for phase, dep in violations
            )
        )


def resolve(skip, add, force=False):
    """Deterministic phase resolver.

    Args:
        skip: set of phase names to exclude
        add: set of phase names to add
        force: when True, allow skipping required phases (specify/implement);
               the dependency check (DepBreak) remains the real backstop

    Returns:
        list of phase names in canonical order

    Raises:
        UnknownPhase (10), SkipAddConflict (11), NotInsertable (12),
        RequiredPhaseSkip (13), DepBreak (14) per validation order
    """
    orderable = set(DEFAULTS) | set(INSERTABLE)

    # 1. Unknown name check
    unknown = (skip | add) - orderable
    if unknown:
        raise UnknownPhase(sorted(unknown), valid=sorted(orderable))

    # 2. Skip/add conflict check
    conflict = skip & add
    if conflict:
        raise SkipAddConflict(sorted(conflict))

    # 3. Add not-insertable check
    not_insertable = add - INSERTABLE
    if not_insertable:
        raise NotInsertable(sorted(not_insertable), INSERTABLE)

    # 4. Required-phase skip check (bypassed with force; DepBreak still guards)
    if not force:
        required_hit = skip & REQUIRED
        if required_hit:
            raise RequiredPhaseSkip(sorted(required_hit))

    # 5. Compute effective set
    effective = (DEFAULTS - skip) | add

    # 6. Dependency-break check: iterate in CANONICAL order, collect ALL violations
    violations = [
        (phase, dep)
        for phase in sorted(effective, key=lambda p: REGISTRY[p].order)
        for dep in REGISTRY[phase].deps
        if dep not in effective
    ]
    if violations:
        raise DepBreak(violations)

    # Return sorted by canonical order
    return sorted(effective, key=lambda p: REGISTRY[p].order)
