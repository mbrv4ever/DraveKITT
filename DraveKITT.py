# -*- coding: utf-8 -*-
"""DraveKITT.py - opstartpunt/launcher. Vangt fouten op in een crashlog,
zodat een fout niet zomaar een zwart venster geeft.
"""
from __future__ import annotations

import os
import sys
import traceback


def _data_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, "DraveKITT-data")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _safe_streams():
    # In een venster-build (geen console) zijn stdout/stderr None; sommige
    # bibliotheken crashen dan bij een print. Stuur ze veilig naar 'niets'.
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")
    except Exception:
        pass


def main():
    _safe_streams()
    try:
        import kitt
        kitt.main()
    except Exception:
        log = os.path.join(_data_dir(), "kitt-fout.txt")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write("DraveKITT is gestopt door een fout:\n\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
