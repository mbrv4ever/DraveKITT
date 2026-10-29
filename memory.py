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


# Het geheugen in laatjes, zoals mensen onthouden (29-10-2026): elk weetje krijgt een laatje.
LAATJES = [
    ("Mensen", "vrouw man vriend vriendin moeder vader zoon dochter broer zus opa oma oom tante kind kinderen "
               "familie collega buurman buurvrouw baas partner neef nicht verjaardag jarig bestuurder "
               "wife husband friend mother father son daughter brother sister family colleague neighbour birthday"),
    ("Dieren", "hond kat poes konijn vogel paard vis huisdier dier dog cat pet horse bird"),
    ("Interesses", "hobby graag leuk favoriet lievelings houd hou muziek film serie boek spel game sport "
                   "voetbal tekenen schilderen koken fotografie like love favourite favorite music movie book"),
    ("Eten", "eten drinken lust allergie allergisch vegetarisch recept koffie thee food drink allergic coffee tea"),
    ("Werk", "werk baan bedrijf kantoor school studie opleiding cursus les job work company office study"),
    ("Thuis", "huis woning adres straat woon woont wonen auto fiets tuin home house address street car garden"),
    ("Afspraken", "afspraak afspraken altijd nooit elke iedere regel herinner remind always never rule"),
    ("KITT", "kitt jij heet voortaan"),
]
LA_OVERIG = "Overig"


_WW_EIND = set("heet heten is ben bent zijn was waren woont woon wonen werkt werk werken houdt hou houden "
               "heeft heb hebt hebben wil wilt willen kan kun kunt kunnen mag mogen moet moeten eet eten "
               "drinkt drink speelt speel rijdt rijd doet doe leest lees zit staat ligt komt kom gaat ga "
               "vindt vind lust lusten studeert studeer verjaart".split())
_ONDERWERP_1 = {"ik", "jij", "je", "hij", "zij", "ze", "wij", "we", "u", "het"}
_LIDWOORD = {"mijn", "m'n", "onze", "ons", "de", "het", "een", "zijn", "haar", "hun", "jouw"}


def hoofdzin(feit):
    """'mijn hond Kira heet' (bijzin na 'onthoud dat') -> 'mijn hond heet Kira' (29-10-2026)."""
    w = (feit or "").split()
    if len(w) < 3 or w[-1].lower() not in _WW_EIND:
        return feit
    if w[0].lower() in _ONDERWERP_1:
        n = 1
    elif w[0].lower() in _LIDWOORD:
        n = 2
    else:
        return feit
    if len(w) <= n + 1:
        return feit
    return " ".join(w[:n] + [w[-1]] + w[n:-1])


def kies_laatje(tekst):
    w = set(re.findall(r"\w+", (tekst or "").lower()))
    beste, score = LA_OVERIG, 0
    for la, woorden in LAATJES:
        n = len(w & set(woorden.split()))
        if n > score:
            beste, score = la, n
    return beste


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
        cur.execute("CREATE TABLE IF NOT EXISTS fact_la (rid INTEGER PRIMARY KEY, la TEXT)")
        self.db.commit()
        # bestaande weetjes (van voor de laatjes) eenmalig een laatje geven
        try:
            rows = cur.execute("SELECT rowid, text FROM mem WHERE role = 'fact' AND rowid NOT IN "
                               "(SELECT rid FROM fact_la)").fetchall()
            cur.executemany("INSERT OR REPLACE INTO fact_la(rid, la) VALUES (?, ?)",
                            [(r[0], kies_laatje(r[1])) for r in rows])
            self.db.commit()
        except Exception:
            pass

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

    def laatje_van(self, rowid):
        if not self.ok:
            return LA_OVERIG
        try:
            with self.lock:
                row = self.db.execute("SELECT la FROM fact_la WHERE rid = ?", (rowid,)).fetchone()
            return row[0] if row else LA_OVERIG
        except Exception:
            return LA_OVERIG

    def facts_voor(self, query, k=8):
        """Weetjes voor het taalmodel: eerst uit het juiste laatje, dan de nieuwste. Met de laatjesnaam ervoor."""
        if not self.ok:
            return []
        la = kies_laatje(query)
        try:
            with self.lock:
                eerst = self.db.execute(
                    "SELECT m.text, f.la FROM mem m JOIN fact_la f ON f.rid = m.rowid "
                    "WHERE m.role = 'fact' AND f.la = ? ORDER BY m.ts DESC LIMIT ?", (la, k)).fetchall()
                rest = self.db.execute(
                    "SELECT m.text, COALESCE(f.la, ?) FROM mem m LEFT JOIN fact_la f ON f.rid = m.rowid "
                    "WHERE m.role = 'fact' ORDER BY m.ts DESC LIMIT ?", (LA_OVERIG, k)).fetchall()
        except Exception:
            return self.recent_facts(k)
        out = []
        for t, l in list(eerst) + list(rest):
            regel = "%s: %s" % (l, (t or "").strip())
            if t and regel not in out:
                out.append(regel)
        return out[:k]

    def delete_fact(self, rowid):
        if not self.ok:
            return
        try:
            with self.lock:
                self.db.execute("DELETE FROM mem WHERE rowid = ?", (rowid,))
                self.db.execute("DELETE FROM fact_la WHERE rid = ?", (rowid,))
                self.db.commit()
        except Exception:
            pass

    def add(self, role, text):
        if not self.ok or not text:
            return
        try:
            with self.lock:
                cur = self.db.execute("INSERT INTO mem(role, text, ts) VALUES (?, ?, ?)",
                                      (role, text.strip(), time.time()))
                if role == "fact":
                    self.db.execute("INSERT OR REPLACE INTO fact_la(rid, la) VALUES (?, ?)",
                                    (cur.lastrowid, kies_laatje(text)))
                self.db.commit()
        except Exception:
            pass

    def remember_fact(self, text):
        """Expliciet een feit opslaan (bv. na 'onthoud dat ...')."""
        self.add("fact", hoofdzin((text or "").strip()))

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
                self.db.execute("DELETE FROM fact_la")
                self.db.commit()
        except Exception:
            pass

    def close(self):
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass
