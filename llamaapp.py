# -*- coding: utf-8 -*-
"""llamaapp.py - KITT's brein via de Llama-app (llama.cpp, lokaal, op de videokaart).

Zelfde vorm als localbrain.LocalBackend, zodat brain.py niets hoeft te weten:
  available(), model_present(), ensure(), chat(messages), close()

Werking:
  * Draait de Llama-app (systeemvak, http://127.0.0.1:9931/v1), dan praat KITT daarmee.
    Hij kiest zelf een model; voorkeur: Fietje (Nederlands), dan Olmo.
  * Is de app er niet, of valt hij weg, dan neemt het eigen model in de app het over
    (LocalBackend, Qwen 2.5 3B via llama-cpp-python). KITT blijft dus altijd praten.

Claudio, 19 okt 2026 - alleen standaardbibliotheek.
"""
from __future__ import annotations

import json
import urllib.request


class LlamaAppBackend:
    def __init__(self, url="http://127.0.0.1:9931/v1", model="", voorkeur=None,
                 terugval=None, timeout=180):
        self.url = (url or "http://127.0.0.1:9931/v1").rstrip("/")
        self.vast = (model or "").strip()
        self.voorkeur = voorkeur or ["fietje", "olmo"]
        self.terugval = terugval          # LocalBackend of None
        self.timeout = timeout
        self.model = None                 # gekozen model-id in de Llama-app
        self.label = ""                   # bv. "eigen motor" als DraveMotor draait (29-10-2026)
        self.loading = False
        self.error = None

    # ---------- de Llama-app ----------
    def _kies(self, timeout=3):
        try:
            with urllib.request.urlopen(self.url + "/models", timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            self.error = str(e)
            return None
        ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        if not ids:
            return None
        if self.vast:
            for i in ids:
                if i.lower() == self.vast.lower():
                    return i
        for v in self.voorkeur:
            for i in ids:
                if v.lower() in i.lower():
                    return i
        return ids[0]

    def app_actief(self):
        return self.model is not None

    def naam(self):
        if self.model:
            if self.label:
                return self.model.split("/")[-1] + " · " + self.label
            return "Llama-app (" + self.model.split("/")[-1] + ")"
        return "eigen model" if self.terugval is not None else "geen"

    # ---------- zelfde vorm als LocalBackend ----------
    def available(self):
        if self.model:
            return True
        return bool(self.terugval and self.terugval.available())

    def model_present(self):
        if self._kies():
            return True
        return bool(self.terugval and self.terugval.model_present())

    def ensure(self):
        self.model = self._kies()
        if self.model:
            return True
        if self.terugval is not None:
            return self.terugval.ensure()
        return False

    def chat(self, messages):
        if self.model is None:
            self.model = self._kies()
        if self.model:
            try:
                body = {"model": self.model, "messages": messages, "stream": False,
                        "temperature": 0.7, "max_tokens": 512, "repeat_penalty": 1.1}
                req = urllib.request.Request(self.url + "/chat/completions",
                                             data=json.dumps(body).encode("utf-8"),
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.loads(r.read().decode("utf-8"))
                return (out["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:
                # app weg of fout -> rustig terugvallen op het eigen model
                self.error = str(e)
                self.model = None
        if self.terugval is not None:
            return self.terugval.chat(messages)
        raise RuntimeError("Llama-app niet bereikbaar: %s" % (self.error or "?"))

    def close(self):
        if self.terugval is not None:
            self.terugval.close()
