# -*- coding: utf-8 -*-
"""memory.py - lokaal langetermijngeheugen voor KITT (SQLite).

Slaat gesprekken en losse feiten op in een kleine lokale database en haalt bij
een nieuwe vraag de relevante stukjes terug, zodat KITT dingen onthoudt over
sessies heen en zo a.h.w. 'leert'. Gebruikt SQLite FTS5 voor zoeken (met een
LIKE-terugval als FTS niet beschikbaar is). Alleen standaardbibliotheek.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time

_STOP = set("de het een en of maar want dus als dat die deze dit ik je jij u wij "
            "we ze zij hij hem haar mijn jouw is ben bent zijn was waren heb hebt "
            "heeft hebben aan op in met voor naar van te der den ook nog wel niet "
            "om over door bij dan toch maar hoe wat wie waar waarom welke".split())


class Memory:
    def __init__(self, path):
        self.ok = False
        self.fts = False
        self.db = None
        self.lock = threading.Lock()
        try:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self._init()
            self.ok = True
        except Exception:
            self.db = None

    def _init(self):
        cur = self.db.cursor()
        try:
            cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem "
                        "USING fts5(role, text, ts UNINDEXED)")
            self.fts = True
        except Exception:
            cur.execute("CREATE TABLE IF NOT EXISTS mem "
                        "(role TEXT, text TEXT, ts REAL)")
            self.fts = False
        cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        self.db.commit()

    def set_meta(self, key, value):
        if not self.ok:
            return
        try:
            with self.lock:
                self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                                (key, value))
                self.db.commit()
        except Exception:
            pass

    def get_meta(self, key, default=""):
        if not self.ok:
            return default
        try:
            with self.lock:
                row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return (row[0] if row else default) or default
        except Exception:
            return default

    def recent_facts(self, k=6):
        if not self.ok:
            return []
        try:
            with self.lock:
                rows = self.db.execute(
                    "SELECT text FROM mem WHERE role = 'fact' ORDER BY ts DESC LIMIT ?",
                    (k,)).fetchall()
            out = []
            for r in rows:
                tt = (r[0] or "").strip()
                if tt and tt not in out:
                    out.append(tt)
            return out
        except Exception:
            return []

    def list_facts(self, limit=40):
        if not self.ok:
            return []
        try:
            with self.lock:
                rows = self.db.execute(
                    "SELECT rowid, text FROM mem WHERE role = 'fact' "
                    "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
            return [(r[0], (r[1] or "").strip()) for r in rows if (r[1] or "").strip()]
        except Exception:
            return []

    def delete_fact(self, rowid):
        if not self.ok:
            return
        try:
            with self.lock:
                self.db.execute("DELETE FROM mem WHERE rowid = ?", (rowid,))
                self.db.commit()
        except Exception:
            pass

    def add(self, role, text):
        if not self.ok or not text:
            return
        try:
            with self.lock:
                self.db.execute("INSERT INTO mem(role, text, ts) VALUES (?, ?, ?)",
                                (role, text.strip(), time.time()))
                self.db.commit()
        except Exception:
            pass

    def remember_fact(self, text):
        """Expliciet een feit opslaan (bv. na 'onthoud dat ...')."""
        self.add("fact", text)

    def _keywords(self, query):
        words = [w for w in re.findall(r"[a-zA-Zà-ÿ0-9]+", query.lower())
                 if len(w) > 3 and w not in _STOP]
        # ontdubbelen, volgorde behouden
        seen = []
        for w in words:
            if w not in seen:
                seen.append(w)
        return seen[:8]

    def recall(self, query, k=4):
        """Geef tot k relevante eerdere fragmenten terug (lege lijst als niets)."""
        if not self.ok:
            return []
        words = self._keywords(query)
        if not words:
            return []
        try:
            with self.lock:
                if self.fts:
                    q = " OR ".join(words)
                    rows = self.db.execute(
                        "SELECT text FROM mem WHERE mem MATCH ? "
                        "ORDER BY rank LIMIT ?", (q, k)).fetchall()
                else:
                    clause = " OR ".join(["lower(text) LIKE ?"] * len(words))
                    args = ["%" + w + "%" for w in words] + [k]
                    rows = self.db.execute(
                        "SELECT text FROM mem WHERE " + clause +
                        " ORDER BY ts DESC LIMIT ?", args).fetchall()
            out = []
            for r in rows:
                t = (r[0] or "").strip()
                if t and t not in out:
                    out.append(t)
            return out
        except Exception:
            return []

    def forget_all(self):
        if not self.ok:
            return
        try:
            with self.lock:
                self.db.execute("DELETE FROM mem")
                self.db.commit()
        except Exception:
            pass

    def close(self):
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass
