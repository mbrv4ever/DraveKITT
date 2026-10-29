# -*- coding: utf-8 -*-
# Copyright (C) 2026 Dravenlock (Roger & Claudio). Licensed under the GNU GPL v3.0 or later - see LICENSE.
"""drave_motor.py - DraveMotor: een eigen, lokaal taalmodel zonder losse app ernaast.

De app start zelf llama.cpp (llama-server, open bron, MIT-licentie) met een klein taalmodel
(standaard Qwen2.5 3B Instruct, Apache-2.0). Werkt op de videokaart via Vulkan (NVIDIA, AMD, Intel),
en anders op de processor. Alles blijft op je eigen pc; alleen het eenmalig downloaden gaat via internet.

- Jij kiest zelf de map waar de motor en het model komen (aanrader: niet op C:).
- Draait de motor al (bijvoorbeeld gestart door een andere Drave-app), dan gebruikt de app die gewoon mee.
- Alleen de standaardbibliotheek.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
import zipfile

POORT = 9941                       # dezelfde poort voor alle Drave-apps: zo delen ze één motor
LLAMA_VERSIE = "b11954"
LLAMA_ZIP = ("https://github.com/ggml-org/llama.cpp/releases/download/%s/llama-%s-bin-win-vulkan-x64.zip"
             % (LLAMA_VERSIE, LLAMA_VERSIE))
MODEL_NAAM = "Qwen2.5 3B"
MODEL_BESTAND = "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
MODEL_URL = "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/" + MODEL_BESTAND
MODEL_MIN = 1_500_000_000          # een volledig model is ~1,9 GB; kleiner = afgebroken download
NO_WIN = 0x08000000 if os.name == "nt" else 0


def standaard_map():
    """Voorstel voor de motor-map: eerst een andere schijf dan C:, anders naast de app."""
    for d in ("D:\\", "E:\\", "F:\\"):
        if os.path.isdir(d):
            return os.path.join(d, "AI-modellen", "DraveMotor")
    return os.path.join(os.path.expanduser("~"), "DraveMotor")


def _bereikbaar(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class Motor:
    def __init__(self, map_pad="", exe="", model="", poort=POORT, naam=MODEL_NAAM, context=8192):
        self.map = map_pad or standaard_map()
        self.exe = exe or os.path.join(self.map, "llama-cpp", "llama-server.exe")
        self.model = model or os.path.join(self.map, MODEL_BESTAND)
        self.poort = int(poort or POORT)
        self.naam = naam or MODEL_NAAM
        self.context = int(context or 8192)
        self.proc = None
        self.eigen_start = False
        self.fout = ""

    # ------------------------------------------------------------ status
    def klaar(self):
        """Staan de motor en het model er (helemaal)?"""
        return (os.path.isfile(self.exe) and os.path.isfile(self.model)
                and os.path.getsize(self.model) >= MODEL_MIN)

    def url(self):
        return "http://127.0.0.1:%d/v1" % self.poort

    def draait(self):
        return _bereikbaar("http://127.0.0.1:%d/health" % self.poort)

    # ------------------------------------------------------------ downloaden
    def _haal(self, url, doel, say, stop, wat):
        tmp = doel + ".part"
        os.makedirs(os.path.dirname(doel), exist_ok=True)
        start = os.path.getsize(tmp) if os.path.exists(tmp) else 0      # afgebroken? verder waar hij was
        req = urllib.request.Request(url, headers={"User-Agent": "DraveMotor"})
        if start:
            req.add_header("Range", "bytes=%d-" % start)
        with urllib.request.urlopen(req, timeout=60) as r:
            if start and r.status != 206:
                start = 0
            totaal = int(r.headers.get("Content-Length") or 0) + start
            gedaan, laatst = start, 0
            with open(tmp, "ab" if start else "wb") as f:
                while True:
                    if stop():
                        raise RuntimeError("Gestopt.")
                    blok = r.read(1 << 20)
                    if not blok:
                        break
                    f.write(blok)
                    gedaan += len(blok)
                    if time.time() - laatst > 1.5:
                        laatst = time.time()
                        pct = (100 * gedaan / totaal) if totaal else 0
                        say("%s: %d%%  (%.0f van %.0f MB)" % (wat, pct, gedaan / 1048576, totaal / 1048576))
        os.replace(tmp, doel)

    def download(self, say=print, stop=lambda: False):
        """Haalt de motor (~37 MB) en het model (~1,9 GB) op naar de gekozen map."""
        os.makedirs(self.map, exist_ok=True)
        if not os.path.isfile(self.exe):
            zp = os.path.join(self.map, os.path.basename(LLAMA_ZIP))
            if not os.path.isfile(zp):
                self._haal(LLAMA_ZIP, zp, say, stop, "Motor")
            say("Motor uitpakken...")
            with zipfile.ZipFile(zp) as z:
                z.extractall(os.path.join(self.map, "llama-cpp"))
            # sommige versies zetten alles in een submap: zoek llama-server.exe op
            for d, _s, fs in os.walk(os.path.join(self.map, "llama-cpp")):
                if "llama-server.exe" in fs:
                    self.exe = os.path.join(d, "llama-server.exe")
                    break
        if not (os.path.isfile(self.model) and os.path.getsize(self.model) >= MODEL_MIN):
            self._haal(MODEL_URL, self.model, say, stop, "Model (%s)" % self.naam)
        if not self.klaar():
            raise RuntimeError("De download is niet compleet. Probeer het nog eens.")
        say("Motor en model staan klaar in %s" % self.map)
        return True

    # ------------------------------------------------------------ starten / stoppen
    def start(self, say=lambda t: None, wacht=240):
        """Start llama-server op de achtergrond (zonder venster). True als hij klaarstaat."""
        if self.draait():
            return True                       # draait al (bv. van Dave of een andere Drave-app)
        if not self.klaar():
            self.fout = "Motor of model ontbreekt."
            return False
        try:
            os.makedirs(self.map, exist_ok=True)   # de map bestond soms nog niet -> log faalde (29-10-2026)
            log = os.path.join(self.map, "motor.log")
            open(log, "ab").close()
        except Exception:
            log = os.path.join(os.path.dirname(self.exe), "motor.log")
        for extra in ([], ["-ngl", "16"]):    # reserve: minder lagen op de videokaart
            args = [self.exe, "-m", self.model, "--host", "127.0.0.1", "--port", str(self.poort),
                    "--alias", self.naam, "-c", str(self.context), "--parallel", "1",
                    "--no-jinja", "--chat-template", "chatml"] + extra
            say("Motor starten%s..." % (" (reserve)" if extra else ""))
            try:
                with open(log, "ab") as lf:
                    self.proc = subprocess.Popen(args, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                                                 cwd=os.path.dirname(self.exe), creationflags=NO_WIN)
            except Exception as e:
                self.fout = str(e)
                return False
            eind = time.time() + wacht
            while time.time() < eind:
                if self.proc.poll() is not None:
                    break
                if self.draait():
                    self.eigen_start = True
                    return True
                time.sleep(1)
            self.stop()
        self.fout = "De motor startte niet (zie %s)." % log
        return False

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.eigen_start = False

    def start_op_achtergrond(self, klaar=lambda ok: None, say=lambda t: None):
        threading.Thread(target=lambda: klaar(self.start(say)), daemon=True).start()


def van_cfg(cfg):
    """Maak een Motor uit de instellingen van een app (sleutels motor_map / motor_exe / motor_model)."""
    return Motor(cfg.get("motor_map", ""), cfg.get("motor_exe", ""), cfg.get("motor_model", ""),
                 cfg.get("motor_poort", POORT), cfg.get("motor_naam", MODEL_NAAM))


def zoek_bestaande():
    """Staat er al een DraveMotor of Dave-motor op deze pc? Geeft (exe, model) of ("", "")."""
    kand = []
    for d in ("C:\\", "D:\\", "E:\\", "F:\\"):
        for sub in ("AI-modellen\\DraveMotor", "AI-modellen\\motor"):
            kand.append(os.path.join(d, sub))
    exe = model = ""
    for k in kand:
        for dd, _s, fs in os.walk(k) if os.path.isdir(k) else []:
            if not exe and "llama-server.exe" in fs:
                exe = os.path.join(dd, "llama-server.exe")
            if not model and MODEL_BESTAND in fs:
                model = os.path.join(dd, MODEL_BESTAND)
    if not model:
        for d in ("C:\\", "D:\\", "E:\\", "F:\\"):
            p = os.path.join(d, "AI-modellen", "gguf", MODEL_BESTAND)
            if os.path.isfile(p):
                model = p
                break
    return exe, model
