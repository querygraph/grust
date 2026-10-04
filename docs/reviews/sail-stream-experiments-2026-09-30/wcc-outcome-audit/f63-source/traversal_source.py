"""The traversal source policy shared by the fixtures, the matrix runner and the cell.

Kept free of third-party imports: `run_matrix.py` runs on the host's Python, which
has neither numpy nor pyarrow.
"""
import argparse
import re

MAX_DEGREE = 'max-degree'


def parse_source(text):
    """A traversal source: a vertex id, or `max-degree` for the highest-degree vertex once prepared."""
    if isinstance(text, int) or text == MAX_DEGREE:
        return text
    if isinstance(text, str) and re.fullmatch(r'[0-9]{1,19}', text):
        return int(text)
    raise argparse.ArgumentTypeError(f'source must be a nonnegative vertex id or {MAX_DEGREE!r}')
