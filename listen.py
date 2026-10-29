# -*- coding: utf-8 -*-
"""listen.py - microfoon (push-to-talk) + spraak-naar-tekst voor KITT.

Werkwijze: houd in de app de spatiebalk ingedrukt om te praten; bij loslaten
wordt de opname naar tekst omgezet. Opnemen via 'sounddevice', transcriberen
via 'faster-whisper' (voorkeur, snel/licht) of anders 'openai-whisper'.

Ontbreekt de microfoon of een whisper-pakket, dan meldt available() False en
kan de app terugvallen op typen.
"""
from __future__ import annotations

import threading

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None


class Ears:
    def __init__(self, model_size="base", lang="nl", samplerate=16000):
        self.model_size = model_size
        self.lang = lang
        self.sr = samplerate
        self._stream = None
        self._chunks = []
        self._recording = False
        self._model = None
        self._backend = None       # "faster" of "openai"
        self._failed_model = False
        self._lock = threading.Lock()

    def available(self):
        return sd is not None and np is not None

    # ---------- opnemen ----------
    def start(self):
        if not self.available() or self._recording:
            return
        self._chunks = []
        try:
            self._stream = sd.InputStream(
                samplerate=self.sr, channels=1, dtype="float32",
                callback=self._cb)
            self._stream.start()
            self._recording = True
        except Exception:
            self._stream = None
            self._recording = False

    def _cb(self, indata, frames, time_info, status):
        try:
            self._chunks.append(indata.copy())
        except Exception:
            pass

    def stop(self):
        """Stop de opname en geef de opgenomen audio (float32 numpy) terug."""
        self._recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        if not self._chunks or np is None:
            return None
        try:
            return np.concatenate(self._chunks, axis=0).flatten().astype("float32")
        except Exception:
            return None

    def recording(self):
        return self._recording

    # ---------- model ----------
    def _ensure_model(self):
        if self._model is not None or self._failed_model:
            return
        with self._lock:
            if self._model is not None or self._failed_model:
                return
            # 1) faster-whisper (aanbevolen)
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device="cpu",
                                           compute_type="int8")
                self._backend = "faster"
                return
            except Exception:
                pass
            # 2) openai-whisper
            try:
                import whisper
                self._model = whisper.load_model(self.model_size)
                self._backend = "openai"
                return
            except Exception:
                self._failed_model = True

    # ---------- transcriberen ----------
    def transcribe(self, audio):
        """Zet opgenomen audio om naar tekst (blokkerend; roep aan in een thread)."""
        if audio is None or np is None or len(audio) < self.sr // 5:
            return ""   # te kort
        self._ensure_model()
        if self._model is None:
            return ""
        try:
            if self._backend == "faster":
                segments, _info = self._model.transcribe(
                    audio, language=self.lang, beam_size=1)
                return "".join(s.text for s in segments).strip()
            else:
                result = self._model.transcribe(
                    audio, language=self.lang, fp16=False)
                return (result.get("text") or "").strip()
        except Exception:
            return ""
