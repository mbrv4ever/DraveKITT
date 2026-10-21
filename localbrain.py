# -*- coding: utf-8 -*-
"""localbrain.py - lokaal taalmodel in de app zelf, zonder Ollama.

Draait een klein GGUF-model rechtstreeks via llama-cpp-python. Het modelbestand
komt in de data-map (DraveKITT-data\\model) en wordt de eerste keer automatisch
gedownload van Hugging Face. Daarna is er geen aparte server (Ollama) nodig.

Standaardmodel: Qwen2.5-3B-Instruct (Q4_K_M, ~2,1 GB) - klein, snel en sterk in
het Nederlands. Te wijzigen in config.json (local_repo / local_file).

Ontbreekt llama-cpp-python of lukt de download niet, dan meldt available() False
en valt de app terug op een nette foutmelding (of op Ollama, als dat is ingesteld).
"""
from __future__ import annotations

import os
import threading


class LocalBackend:
    def __init__(self, repo, filename, data_dir, n_ctx=4096, n_threads=None):
        self.repo = repo
        self.filename = filename
        self.data_dir = data_dir
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.llm = None
        self.failed = False
        self.loading = False
        self.error = None
        self._lock = threading.Lock()

    def available(self):
        return self.llm is not None

    def model_dir(self):
        d = os.path.join(self.data_dir, "model")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def model_present(self):
        """True als het modelbestand al gedownload is (dus geen download nodig)."""
        md = self.model_dir()
        try:
            if os.path.isfile(os.path.join(md, self.filename)):
                return True
            # terugval: een willekeurig .gguf-bestand ergens in de modelmap
            for root, _dirs, files in os.walk(md):
                for f in files:
                    if f.lower().endswith(".gguf"):
                        return True
        except Exception:
            pass
        return False

    def ensure(self):
        """Laad het model (download het de eerste keer). True als het klaar is."""
        if self.llm is not None:
            return True
        if self.failed:
            return False
        with self._lock:
            if self.llm is not None:
                return True
            if self.failed:
                return False
            self.loading = True
            try:
                # Sommige pc's hebben kapotte HIP_PATH/CUDA_PATH-variabelen (bv.
                # een oude AMD ROCm-installatie). llama-cpp-python probeert die
                # map als DLL-pad toe te voegen en crasht als hij niet bestaat.
                # Verwijder zulke verwijzingen vóór het importeren (CPU-wheel
                # heeft ze niet nodig).
                for _var in ("HIP_PATH", "HIP_PATH_57", "HIPSDK_PATH", "CUDA_PATH"):
                    _p = os.environ.get(_var)
                    if _p and not os.path.isdir(os.path.join(_p, "bin")):
                        os.environ.pop(_var, None)
                from llama_cpp import Llama
                kw = dict(repo_id=self.repo, filename=self.filename,
                          local_dir=self.model_dir(), n_ctx=self.n_ctx, verbose=False)
                if self.n_threads:
                    kw["n_threads"] = self.n_threads
                self.llm = Llama.from_pretrained(**kw)
            except Exception as e:
                self.failed = True
                import traceback
                self.error = str(e)
                try:
                    with open(os.path.join(self.data_dir, "kitt-model-fout.txt"),
                              "w", encoding="utf-8") as f:
                        f.write("Het lokale model kon niet geladen worden.\n\n")
                        f.write("Repo: %s\nBestand: %s\n\n" % (self.repo, self.filename))
                        f.write(traceback.format_exc())
                        f.write("\n\nTip: lukt llama-cpp-python niet op deze pc, zet "
                                "dan in config.json \"backend\": \"ollama\".")
                except Exception:
                    pass
            finally:
                self.loading = False
        return self.llm is not None

    def chat(self, messages):
        """Chat-aanroep (zelfde vorm als de Ollama-backend): geeft tekst terug."""
        if not self.ensure():
            raise RuntimeError("lokaal model niet beschikbaar: %s" % (self.error or "?"))
        out = self.llm.create_chat_completion(
            messages=messages, temperature=0.7, max_tokens=512)
        try:
            return (out["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            return ""

    def close(self):
        # geheugen vrijgeven; llama.cpp ruimt zichzelf op bij GC
        self.llm = None
