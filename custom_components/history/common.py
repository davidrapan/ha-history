from __future__ import annotations

import logging

from pathlib import Path

_LOGGER = logging.getLogger(__name__)

def open_file(filepath, mode, x):
    file_path = Path(filepath)
    file_path.parent.mkdir(exist_ok = True, parents = True)
    with open(filepath, mode) as file:
        return x(file)