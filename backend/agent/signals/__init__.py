"""Per-source signal builders for the SignalBoard.

Each module exposes `def collect(as_of_date) -> list[Signal]`. Build phase 2
of §13 will populate one file per source from §4.1.
"""
