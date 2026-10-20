# -*- coding: utf-8 -*-
"""search.py - online zoeken voor KITT.

Standaard via Startpage (privacyvriendelijk). Startpage heeft geen officiele API
en blokkeert soms geautomatiseerde verzoeken; lukt het niet, dan valt KITT
automatisch terug op DuckDuckGo (pakket 'ddgs'), zodat zoeken blijft werken.
In te stellen met "search_engine" in config.json: "startpage" of "duckduckgo".
Alleen het Startpage-pad gebruikt de standaardbibliotheek (urllib).
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class Search:
    def __init__(self, engine="startpage", max_results=5):
        self.engine = (engine or "startpage").lower()
        self.max_results = max_results
        self._ddgs = None
        self._ddgs_checked = False

    def available(self):
        # Startpage werkt via urllib (altijd aanwezig); DuckDuckGo vereist 'ddgs'.
        if self.engine == "duckduckgo":
            return self._load_ddgs()
        return True

    # ---------- publiek ----------
    def search(self, query, k=None):
        q = (query or "").strip()
        if not q:
            return ""
        k = k or self.max_results
        if self.engine == "duckduckgo":
            return self._duck(q, k)
        # startpage (standaard) met terugval naar duckduckgo
        res = self._startpage(q, k)
        if not res:
            res = self._duck(q, k)
        return res

    # ---------- Startpage ----------
    def _startpage(self, q, k):
        try:
            url = "https://www.startpage.com/sp/search?" + urllib.parse.urlencode(
                {"query": q, "language": "nederlands"})
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Accept-Language": "nl,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=12) as r:
                page = r.read().decode("utf-8", "ignore")
            descs = re.findall(r'class="w-gl__description[^"]*"[^>]*>(.*?)</p>', page, re.S)
            titles = re.findall(r'class="w-gl__result-title[^"]*"[^>]*>(.*?)</a>', page, re.S)
            out = []
            for i, d in enumerate(descs[:k]):
                t = self._clean(titles[i]) if i < len(titles) else ""
                body = self._clean(d)
                if body:
                    line = ("%s: %s" % (t, body)).strip(" :")
                    out.append("- " + line)
            return "\n".join(out)
        except Exception:
            return ""

    @staticmethod
    def _clean(s):
        s = re.sub(r"<[^>]+>", "", s or "")
        return html.unescape(s).strip()

    # ---------- DuckDuckGo (terugval) ----------
    def _load_ddgs(self):
        if self._ddgs_checked:
            return self._ddgs is not None
        self._ddgs_checked = True
        try:
            from ddgs import DDGS
            self._ddgs = DDGS
        except Exception:
            try:
                from duckduckgo_search import DDGS
                self._ddgs = DDGS
            except Exception:
                self._ddgs = None
        return self._ddgs is not None

    def _duck(self, q, k):
        if not self._load_ddgs():
            return ""
        try:
            out = []
            with self._ddgs() as ddgs:
                for r in ddgs.text(q, max_results=k):
                    title = (r.get("title") or "").strip()
                    body = (r.get("body") or r.get("snippet") or "").strip()
                    if title or body:
                        out.append("- %s: %s" % (title, body))
            return "\n".join(out[:k])
        except Exception:
            return ""
