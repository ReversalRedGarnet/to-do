"""Unit tests for core.state_engine.reconcile. See spec §19, §54.

Required gap scenarios: 0, 1, 5, and 10+ days, including gaps that cross
one and two weekly boundaries. This is the most safety-critical module
in the app — do not skip edge cases here.
"""

# TODO:
# - previous day closes correctly
# - new day becomes active
# - missed tasks are reconciled
# - schedule recalculates
# - multi-day gap replays each day in order
# - gap crossing a week boundary triggers history archive + purge
