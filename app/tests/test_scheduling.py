"""Unit tests for core.scheduling_engine. See spec §54."""

# TODO:
# - tasks cannot be scheduled before available_from
# - tasks cannot be scheduled after due_date
# - fixed events remain fixed
# - tasks distribute across days
# - scheduler preserves slack (does not exceed UTILIZATION_TARGET)
# - large tasks can span multiple days
# - low-priority work does not crowd out imminent critical work
