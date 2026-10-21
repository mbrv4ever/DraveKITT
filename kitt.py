# -*- coding: utf-8 -*-
"""kitt.py - DraveKITT: een KITT-achtige voice box (Dravenlock-stijl).

Praat met je auto-AI: houd SPATIE ingedrukt om te praten (push-to-talk), laat
los en KITT antwoordt met stem terwijl de rode balkjes meebewegen. Brein via
een lokaal Ollama-model, spraak-naar-tekst via Whisper, stem via neuvoice.

Werkt ook deels als een onderdeel ontbreekt: het dashboard start altijd, en
je kunt met T overschakelen naar typen. Geen echte Knight Rider-audio/logo's.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import threading
import time
import webbrowser

import pygame

from voicebox import KittPanel, MUTE, GREEN, AMBER, SEG_ON, GOLD
from speak import KittVoice
from brain import Brain
from listen import Ears
from memory import Memory
from search import Search
from localbrain import LocalBackend
from llamaapp import LlamaAppBackend

WIDTH, HEIGHT = 900, 560
FPS = 60

DONATE_URL = "https://paypal.me/roger076"
CONTACT_EMAIL = "service@dravenlock.nl"

# Engelstalige begroeting (KITT-referentie). {name} wordt vervangen door de naam.
DEFAULT_GREETING = (
    "All systems online. I am the voice of Knight Industries Two Thousand. "
    "KITT, for short.{name} I am at your service, as always."
)


def data_dir():
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


def load_config():
    cfg = {
        "backend": "auto",           # "auto" = Llama-app, anders eigen model | "local" | "ollama"
        "llama_url": "http://127.0.0.1:9931/v1",
        "llama_model": "",           # leeg = KITT kiest zelf (voorkeur hieronder)
        "llama_voorkeur": ["fietje", "olmo"],
        "local_repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "local_file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "model": "llama3.2",         # alleen voor backend "ollama"
        "ollama_host": "http://localhost:11434",
        "voice_name": "M1",
        "voice_speed": 1.0,
        "voice_pitch": 1.0,
        "voice_volume": 1.0,
        "voice_on": True,
        "lang": "nl",
        "whisper_size": "base",
        "autostart_ollama": True,
        "stop_ollama_on_exit": True,
        "online_search": True,
        "search_engine": "startpage",   # "startpage" (privacy) of "duckduckgo"
        "auto_learn": True,
        "greeted": False,
        "greeting": DEFAULT_GREETING,
        "user_name": "",
        "instructions": "",          # vaste richtlijnen (Geheugen-scherm)
        "ui_scale": 1.0,             # tekstgrootte (toegankelijkheid)
    }
    try:
        with open(os.path.join(data_dir(), "config.json"), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(os.path.join(data_dir(), "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


class App:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.cfg = load_config()
        self.panel = KittPanel()
        self.voice = KittVoice(voice=self.cfg["voice_name"], lang=self.cfg["lang"],
                               data_dir=data_dir())
        self.voice.speed = self.cfg.get("voice_speed", 1.0)
        self.voice.pitch = self.cfg.get("voice_pitch", 1.0)
        self.voice.volume = self.cfg.get("voice_volume", 1.0)
        self.voice.enabled = self.cfg.get("voice_on", True)
        self.brain = Brain(host=self.cfg["ollama_host"], model=self.cfg["model"])
        # backend kiezen: lokaal model in de app (geen Ollama) of Ollama-server
        backend = self.cfg.get("backend", "auto")
        if backend in ("auto", "llama", "local"):
            eigen = LocalBackend(self.cfg["local_repo"], self.cfg["local_file"], data_dir())
            if backend == "local":
                self.brain.local = eigen          # alleen het eigen model in de app
            else:
                # eerst de Llama-app (videokaart), anders het eigen model als terugval
                self.brain.local = LlamaAppBackend(self.cfg.get("llama_url", "http://127.0.0.1:9931/v1"),
                                                   self.cfg.get("llama_model", ""),
                                                   self.cfg.get("llama_voorkeur", ["fietje", "olmo"]),
                                                   terugval=eigen)
        self.ears = Ears(model_size=self.cfg["whisper_size"], lang=self.cfg["lang"])
        # geheugen + online zoeken aan het brein koppelen
        self.memory = Memory(os.path.join(data_dir(), "kitt-geheugen.db"))
        self.brain.memory = self.memory
        if self.cfg.get("online_search", True):
            self.brain.search = Search(engine=self.cfg.get("search_engine", "startpage"))
        self.brain.user_name = self.cfg.get("user_name", "")
        # namen + richtlijnen herstellen uit het geheugen (blijven bewaard)
        if self.memory:
            saved_user = self.memory.get_meta("user_name", "")
            if saved_user:
                self.brain.user_name = saved_user
                self.cfg["user_name"] = saved_user
            self.brain.assistant_name = self.memory.get_meta("assistant_name", "")
        self.brain.instructions = self.cfg.get("instructions", "")
        self.brain.stop_ollama_on_exit = self.cfg.get("stop_ollama_on_exit", True)
        self.brain.auto_learn = self.cfg.get("auto_learn", True)
        self.state = "idle"          # idle / listening / thinking / searching / speaking
        self.busy = False            # er loopt een verwerk-thread
        self.last_user = ""
        self.last_reply = ""
        self.typing = False
        self.type_text = ""
        self.ollama_ok = None
        self.loading = False         # model wordt geladen/gedownload
        self.load_msg = "Model laden..."
        self.need_model = False      # chatmodel nog niet binnen -> eerst toestemming vragen
        self.model_btn_rect = None   # klikzone van de download-knop
        self.in_settings = False     # stem-instellingenscherm open
        self.set_idx = 0
        self.set_hits = []           # klikbare rects in het instellingenscherm
        self.in_memory = False       # geheugen-scherm open (F3)
        self.mem_instr = self.cfg.get("instructions", "")  # bewerkbare richtlijnen
        self.mem_hits = []           # klikbare rects (weetje verwijderen e.d.)
        self.mem_scroll = 0
        self.show_help = False       # snelgids-overlay
        self.help_hits = []          # klikbare rects in de snelgids
        self.util_hits = []          # zichtbare knoppen linksboven (stem/geheugen/gids/doneer)
        self.pending = None          # wacht op invoer voor een knop (weer/nieuws)
        self.btn_flash = ""          # laatst ingedrukte zijknop (oplichten)
        self.btn_flash_until = 0.0
        # eerste keer: naam vragen
        self.asking_name = not self.cfg.get("user_name")
        self.name_text = ""
        self.ui_scale = float(self.cfg.get("ui_scale", 1.0))
        self._build_fonts()
        self.ready = False           # klaar met opstarten (voor het splashscherm)
        threading.Thread(target=self._startup, daemon=True).start()

    def _build_fonts(self):
        """(Her)maak lettertypes op basis van ui_scale (toegankelijkheid)."""
        sc = self.ui_scale
        self.font = pygame.font.Font(None, max(16, int(26 * sc)))
        self.font_s = pygame.font.Font(None, max(14, int(22 * sc)))
        self.font_l = pygame.font.Font(None, max(24, int(40 * sc)))
        self.font_in = pygame.font.Font(None, max(20, int(30 * sc)))  # invoervak, groter
        self.font_btn = pygame.font.Font(None, 22)   # util-knoppen: VAST (anders te breed)

    def _greet(self):
        name = self.cfg.get("user_name", "")
        tmpl = self.cfg.get("greeting", DEFAULT_GREETING)
        text = tmpl.replace("{name}", (" " + name + ",") if name else "")
        self.state = "speaking"
        self.voice.speak_sync(text, lang="en")
        self.state = "idle"
        self.cfg["greeted"] = True
        save_config(self.cfg)

    def _startup(self):
        # 0) stem voorbereiden (gebeurt nu op de achtergrond i.p.v. bij het opstarten,
        #    zodat het splashscherm dit netjes afdekt)
        try:
            self.voice.warmup()
        except Exception:
            pass
        # 1) begroeting (alleen als naam al bekend is; anders na het invoeren)
        if not self.asking_name and not self.cfg.get("greeted"):
            self._greet()
        # 2) brein klaarzetten: lokaal model laden, of Ollama starten
        if self.brain.local is not None:
            if self.brain.local.model_present():
                # model staat er al -> gewoon laden
                self.load_msg = "Model laden..."
                self.loading = True
                self.ollama_ok = self.brain.local.ensure()
                self.loading = False
            else:
                # nog geen model -> NIET stiekem downloaden; eerst vragen
                self.need_model = True
        elif self.cfg.get("autostart_ollama", True):
            self.ollama_ok = self.brain.ensure_running()
        else:
            self.ollama_ok = self.brain.reachable()
        self.ready = True            # opstarten klaar -> splashscherm mag sluiten

    def _start_model_download(self):
        """Pas NA toestemming: het chatmodel ophalen (eenmalig, ~2 GB)."""
        if self.loading:
            return
        self.need_model = False
        self.model_btn_rect = None
        self.load_msg = "Model downloaden... (eenmalig, kan even duren)"
        self.loading = True

        def work():
            try:
                ok = self.brain.local.ensure()
            except Exception:
                ok = False
            self.ollama_ok = ok
            self.loading = False
            if not ok:
                self.need_model = not self.brain.local.model_present()
        threading.Thread(target=work, daemon=True).start()

    def _draw_model_consent(self, s):
        """Vriendelijke melding + download-knop als het chatmodel nog mist."""
        cy = HEIGHT // 2 - 70
        self._center(s, "Voor de chat is eenmalig een taalmodel nodig", self.font,
                     (220, 220, 225), cy)
        self._center(s, "(ongeveer 2 GB, wordt naar DraveKITT-data gedownload).",
                     self.font_s, MUTE, cy + 30)
        self._center(s, "Niets wordt zonder jouw 'ja' gedownload.",
                     self.font_s, MUTE, cy + 52)
        bw, bh = 380, 54
        r = pygame.Rect(WIDTH // 2 - bw // 2, cy + 84, bw, bh)
        pygame.draw.rect(s, (20, 20, 24), r, border_radius=10)
        pygame.draw.rect(s, GREEN, r, width=2, border_radius=10)
        self._blit_center(s, "Taalmodel downloaden (~2 GB)", self.font, GREEN, r)
        self.model_btn_rect = r

    def _save_name(self):
        name = self.name_text.strip()[:24]
        self.asking_name = False
        self.name_text = ""
        if name:
            self.cfg["user_name"] = name
            self.brain.user_name = name
            save_config(self.cfg)
            if self.memory:
                self.memory.set_meta("user_name", name)
                self.memory.remember_fact("De bestuurder heet %s." % name)
        # na het invoeren van de naam stelt KITT zich voor (met je naam erin)
        threading.Thread(target=self._greet, daemon=True).start()

    def _on_status(self, status):
        # callback vanuit het brein tijdens het zoeken
        if status in ("searching", "thinking", "speaking"):
            self.state = status

    # ---------- helpers voor knoppen ----------
    def _say(self, text):
        self.last_reply = text
        self.state = "speaking"
        self.voice.speak_sync(text)

    def _ask_and_say(self, prompt, shown="(knop)"):
        self.last_user = shown
        self.state = "thinking"
        reply = self.brain.ask(prompt, on_status=self._on_status)
        self.last_reply = reply
        self.state = "speaking"
        self.voice.speak_sync(reply)

    # ---------- de functies achter de zijknoppen ----------
    def _b_clock(self):
        now = datetime.datetime.now()
        dagen = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
                 "zaterdag", "zondag"]
        self._say("Het is %d uur %02d, op %s." % (now.hour, now.minute, dagen[now.weekday()]))

    def _b_battery(self):
        pct = None
        try:
            import psutil
            b = psutil.sensors_battery()
            if b is not None:
                pct = int(b.percent)
        except Exception:
            pct = None
        if pct is None:
            self._say("Energiestatus onbekend, maar alle systemen draaien naar behoren.")
        else:
            self._say("Energiereserve op %d procent." % pct)

    def _b_syscheck(self):
        self._say("Diagnose voltooid. Alle systemen functioneren naar behoren.")

    def _b_joke(self):
        self._ask_and_say("Vertel een korte, originele grap in het Nederlands.", "Grapje?")

    def _b_repeat(self):
        self._say(self.last_reply or "Ik heb nog niets gezegd om te herhalen.")

    def _b_newchat(self):
        self.brain.reset()
        self._say("Nieuw gesprek gestart. Ik luister.")

    def _b_scan(self):
        self._say("Scan voltooid. Geen bedreigingen gedetecteerd in de directe omgeving.")

    def _b_help(self):
        self._say("Houd de spatiebalk ingedrukt om te praten, of typ je vraag. "
                  "Met de knoppen vraag je tijd, energie, weer, nieuws en meer.")

    # knoppen die eerst om invoer vragen (typen of inspreken)
    _INPUT_BTN = {"WEER": "weather", "NIEUWS": "news"}

    def _buttons_map(self):
        return {
            "TIJD": self._b_clock, "ACCU": self._b_battery,
            "SYSTEEM": self._b_syscheck, "GRAP": self._b_joke,
            "HERHAAL": self._b_repeat, "NIEUW": self._b_newchat,
            "SCAN": self._b_scan, "HULP": self._b_help,
        }

    def _button_press(self, label):
        if self.busy or self.asking_name or self.in_settings:
            return
        self.btn_flash = label
        self.btn_flash_until = time.time() + 0.5
        # weer/nieuws: eerst om stad/bron vragen (typen of inspreken)
        need = self._INPUT_BTN.get(label)
        if need:
            self.pending = need
            return
        fn = self._buttons_map().get(label)
        if not fn:
            return
        self.pending = None
        self.busy = True
        threading.Thread(target=self._run_button, args=(fn,), daemon=True).start()

    def _run_button(self, fn):
        try:
            fn()
        except Exception:
            pass
        finally:
            self.state = "idle"
            self.busy = False

    # ---------- stem-instellingen ----------
    def _settings_key(self, e):
        if e.key in (pygame.K_ESCAPE, pygame.K_F2):
            self.in_settings = False
            self._save_voice_cfg()
        elif e.key in (pygame.K_UP, pygame.K_w):
            self.set_idx = (self.set_idx - 1) % 6
        elif e.key in (pygame.K_DOWN, pygame.K_s):
            self.set_idx = (self.set_idx + 1) % 6
        elif e.key in (pygame.K_LEFT, pygame.K_a):
            self._set_adjust(-1)
        elif e.key in (pygame.K_RIGHT, pygame.K_d):
            self._set_adjust(1)
        elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
            if not self.busy:
                threading.Thread(
                    target=lambda: self.voice.speak_sync(
                        "Hallo, dit is een test van mijn stem."),
                    daemon=True).start()

    def _settings_click(self, pos):
        for kind, i, d, rect in self.set_hits:
            if rect.collidepoint(pos):
                if kind == "adj":
                    self.set_idx = i
                    self._set_adjust(d)
                elif kind == "sel":
                    self.set_idx = i
                elif kind == "test":
                    if not self.busy:
                        threading.Thread(
                            target=lambda: self.voice.speak_sync(
                                "Hallo, dit is een test van mijn stem."),
                            daemon=True).start()
                elif kind == "close":
                    self.in_settings = False
                    self._save_voice_cfg()
                return

    def _set_adjust(self, d):
        i = self.set_idx
        if i == 0:   # stem kiezen
            vs = self.voice.list_voices()
            if vs:
                try:
                    cur = vs.index(self.voice.voice)
                except ValueError:
                    cur = 0
                self.voice.set_voice(vs[(cur + d) % len(vs)])
        elif i == 1:
            self.voice.speed = round(min(1.6, max(0.6, self.voice.speed + 0.05 * d)), 2)
        elif i == 2:
            self.voice.pitch = round(min(1.3, max(0.8, self.voice.pitch + 0.05 * d)), 2)
        elif i == 3:
            self.voice.volume = round(min(1.0, max(0.0, self.voice.volume + 0.1 * d)), 2)
        elif i == 4:
            self.voice.enabled = not self.voice.enabled
        elif i == 5:
            scales = [1.0, 1.25, 1.5]
            try:
                idx = scales.index(round(self.ui_scale, 2))
            except ValueError:
                idx = 0
            self.ui_scale = scales[(idx + d) % len(scales)]
            self._build_fonts()
            self.cfg["ui_scale"] = self.ui_scale
            save_config(self.cfg)

    def _save_voice_cfg(self):
        self.cfg["voice_name"] = self.voice.voice
        self.cfg["voice_speed"] = self.voice.speed
        self.cfg["voice_pitch"] = self.voice.pitch
        self.cfg["voice_volume"] = self.voice.volume
        self.cfg["voice_on"] = self.voice.enabled
        save_config(self.cfg)

    # ---------- geheugen-scherm (F3) ----------
    def _open_memory(self):
        self.in_memory = True
        self.mem_instr = self.brain.instructions
        self.mem_scroll = 0

    def _save_instructions(self):
        self.cfg["instructions"] = self.mem_instr
        save_config(self.cfg)
        self.brain.instructions = self.mem_instr

    def _memory_key(self, e):
        if e.key in (pygame.K_ESCAPE, pygame.K_F3):
            self._save_instructions()
            self.in_memory = False
        elif e.key == pygame.K_RETURN:
            self.mem_instr += "\n"
        elif e.key == pygame.K_BACKSPACE:
            self.mem_instr = self.mem_instr[:-1]

    def _memory_click(self, pos):
        for kind, val, rect in self.mem_hits:
            if rect.collidepoint(pos):
                if kind == "del" and self.memory:
                    self.memory.delete_fact(val)
                elif kind == "forget" and self.memory:
                    self.memory.forget_all()
                elif kind == "close":
                    self._save_instructions()
                    self.in_memory = False
                return

    def _memory_panel(self, t):
        s = self.screen
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 210))
        s.blit(ov, (0, 0))
        self.mem_hits = []
        self._center(s, "Geheugen", self.font_l, GREEN, 44)
        # 1) vaste richtlijnen (bewerkbaar)
        s.blit(self.font_s.render("Vaste richtlijnen - wat KITT wel/niet mag, "
                                  "voorkeuren (Enter = nieuwe regel):", True, MUTE),
               (30, 78))
        box = pygame.Rect(30, 100, WIDTH - 60, 120)
        pygame.draw.rect(s, (20, 20, 24), box, border_radius=8)
        pygame.draw.rect(s, GREEN, box, width=2, border_radius=8)
        disp = self.mem_instr + ("_" if (t % 1.0) < 0.5 else "")
        lines = disp.split("\n") if disp else [""]
        yy = box.y + 8
        for ln in lines[-5:]:
            while self.font_s.size(ln)[0] > box.w - 20 and len(ln) > 1:
                ln = ln[1:]
            s.blit(self.font_s.render(ln, True, (225, 225, 230)), (box.x + 10, yy))
            yy += 22
        # 2) opgeslagen weetjes (verwijderbaar)
        s.blit(self.font_s.render("Onthouden weetjes (klik X om te verwijderen):",
                                  True, MUTE), (30, 232))
        facts = self.memory.list_facts(20) if self.memory else []
        ly = 258
        bottom = HEIGHT - 70
        if not facts:
            s.blit(self.font_s.render("(nog niets onthouden)", True, MUTE), (46, ly))
        for rowid, txt in facts:
            if ly > bottom - 26:
                s.blit(self.font_s.render("...en meer", True, MUTE), (46, ly))
                break
            xr = pygame.Rect(30, ly, 28, 24)
            pygame.draw.rect(s, (40, 26, 26), xr, border_radius=5)
            pygame.draw.rect(s, (200, 90, 80), xr, width=2, border_radius=5)
            self._blit_center(s, "X", self.font_s, (230, 120, 110), xr)
            self.mem_hits.append(("del", rowid, xr))
            line = txt
            while self.font_s.size(line)[0] > WIDTH - 110 and len(line) > 1:
                line = line[:-1]
            s.blit(self.font_s.render(line, True, (220, 220, 225)), (68, ly + 2))
            ly += 30
        # knoppen onderaan
        forget_rect = pygame.Rect(30, HEIGHT - 54, 210, 38)
        close_rect = pygame.Rect(WIDTH - 200, HEIGHT - 54, 170, 38)
        pygame.draw.rect(s, (40, 26, 26), forget_rect, border_radius=8)
        pygame.draw.rect(s, (200, 90, 80), forget_rect, width=2, border_radius=8)
        self._blit_center(s, "Wis ALLE weetjes", self.font_s, (230, 150, 140), forget_rect)
        pygame.draw.rect(s, (24, 32, 24), close_rect, border_radius=8)
        pygame.draw.rect(s, GREEN, close_rect, width=2, border_radius=8)
        self._blit_center(s, "Opslaan & sluiten", self.font_s, (200, 230, 200), close_rect)
        self.mem_hits.append(("forget", 0, forget_rect))
        self.mem_hits.append(("close", 0, close_rect))

    # ---------- snelgids (F1) ----------
    def _help_click(self, pos):
        for kind, rect in self.help_hits:
            if rect.collidepoint(pos):
                if kind == "donate":
                    try:
                        webbrowser.open(DONATE_URL)
                    except Exception:
                        pass
                elif kind == "close":
                    self.show_help = False
                return

    def _help_panel(self, t):
        s = self.screen
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 215))
        s.blit(ov, (0, 0))
        self.help_hits = []
        self._center(s, "Snelgids - DraveKITT", self.font_l, GREEN, 40)
        lines = [
            "Houd SPATIE ingedrukt om te praten; laat los en KITT antwoordt.",
            "Of typ gewoon je vraag (Enter = versturen, Esc = annuleren).",
            "Zijknoppen: tijd, energie, weer, nieuws, grap, scan en meer.",
            "WEER/NIEUWS vragen eerst om een stad/bron (typ of spreek in).",
            "F2 = stem-instellingen.  F3 = geheugen (richtlijnen + weetjes).",
            "Hernoemen: 'ik noem je X'.  Je naam: 'ik heet X'.",
            "'onthoud dat ...' bewaart een vast weetje.",
            "F1 = deze gids aan/uit.  Esc = sluiten.",
        ]
        y = 92
        for ln in lines:
            s.blit(self.font_s.render("- " + ln, True, (225, 225, 230)), (40, y))
            y += 30
        y += 8
        s.blit(self.font_s.render("Bevalt DraveKITT? Steun de ontwikkeling met een "
                                  "kleine donatie - dank je wel!", True, MUTE), (40, y))
        y += 30
        dr = pygame.Rect(40, y, 240, 44)
        pygame.draw.rect(s, (24, 32, 24), dr, border_radius=8)
        pygame.draw.rect(s, GREEN, dr, width=2, border_radius=8)
        self._blit_center(s, "Doneer via PayPal", self.font_s, (200, 230, 200), dr)
        self.help_hits.append(("donate", dr))
        s.blit(self.font_s.render("Contact: " + CONTACT_EMAIL, True, MUTE),
               (dr.right + 24, y + 12))
        cr = pygame.Rect(WIDTH - 170, HEIGHT - 60, 140, 42)
        pygame.draw.rect(s, (28, 28, 34), cr, border_radius=8)
        pygame.draw.rect(s, AMBER, cr, width=2, border_radius=8)
        self._blit_center(s, "Sluiten", self.font_s, (235, 235, 240), cr)
        self.help_hits.append(("close", cr))

    # ---------- echte weergegevens (wttr.in, gratis, geen sleutel) ----------
    def _fetch_weather(self, city):
        import urllib.parse
        import urllib.request
        url = ("https://wttr.in/%s?format=%%C,+%%t+(gevoelstemperatuur+%%f),+"
               "wind+%%w,+luchtvochtigheid+%%h&lang=nl&m"
               % urllib.parse.quote(city.strip()))
        # een 'curl'-achtige user-agent geeft de korte tekstversie i.p.v. HTML
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode("utf-8", "replace").strip()
        # spraakvriendelijk maken (pijltjes/tekens weg)
        for a in "←↑→↓↖↗↘↙":
            txt = txt.replace(a, "")
        txt = (txt.replace("°C", " graden").replace("+", "")
               .replace("km/h", " kilometer per uur").replace("%", " procent"))
        return " ".join(txt.split())

    # ---------- verwerking ----------
    def _handle(self, user_text):
        """Transcriptie/typtekst -> (evt. weer/nieuws-opdracht) -> brein -> stem."""
        try:
            pend = self.pending
            self.pending = None
            if pend == "weather":
                # ECHTE actuele weergegevens ophalen i.p.v. het model laten gokken
                self.last_user = "Weer: " + user_text
                self.state = "searching"
                stad = user_text.strip()
                data = ""
                try:
                    data = self._fetch_weather(stad)
                except Exception:
                    data = ""
                if data and "Unknown location" not in data and "not found" not in data.lower():
                    reply = "Het actuele weer in %s: %s." % (stad, data)
                else:
                    reply = ("Ik kon het actuele weer voor %s niet ophalen. "
                             "Controleer de plaatsnaam of je internetverbinding." % stad)
                self.last_reply = reply
                self.state = "speaking"
                self.voice.speak_sync(reply)
                return
            if pend == "news":
                shown = "Nieuws: " + user_text
                user_text = ("Geef het belangrijkste nieuws van vandaag van de bron "
                             "%s. Vat het kort samen." % user_text)
            else:
                shown = user_text
            self.last_user = shown
            if self.need_model:
                # geen stiekeme download: vraag eerst om de download-knop
                self.last_reply = ("Hiervoor heb ik eerst een taalmodel nodig. "
                                   "Klik op 'Taalmodel downloaden' op het scherm.")
                self.state = "speaking"
                self.voice.speak_sync("Hiervoor heb ik eerst een taalmodel nodig. "
                                      "Klik op de download-knop op het scherm.")
                return
            self.state = "thinking"
            reply = self.brain.ask(user_text, on_status=self._on_status)
            self.last_reply = reply
            self.state = "speaking"
            self.voice.speak_sync(reply)
        except Exception:
            pass
        finally:
            self.state = "idle"
            self.busy = False

    def _handle_audio(self, audio):
        try:
            self.state = "thinking"
            text = self.ears.transcribe(audio)
            if not text:
                self.last_reply = "(niets verstaan)"
                self.state = "idle"
                self.busy = False
                return
            self._handle(text)
        except Exception:
            self.state = "idle"
            self.busy = False

    def _send_typed(self):
        text = self.type_text.strip()
        self.type_text = ""
        self.typing = False
        if text and not self.busy:
            self.busy = True
            threading.Thread(target=self._handle, args=(text,), daemon=True).start()

    # ---------- events ----------
    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                self._keydown(e)
            elif e.type == pygame.TEXTINPUT:
                self._textinput(e.text)
            elif e.type == pygame.KEYUP:
                if e.key == pygame.K_SPACE and self.state == "listening":
                    self._stop_listening()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if self.show_help:
                    self._help_click(e.pos)
                elif self.in_settings:
                    self._settings_click(e.pos)
                elif self.in_memory:
                    self._memory_click(e.pos)
                elif (self.need_model and self.model_btn_rect
                      and self.model_btn_rect.collidepoint(e.pos)):
                    self._start_model_download()
                elif not self.asking_name:
                    if not self._util_click(e.pos):
                        for lbl, rect in list(self.panel.buttons.items()):
                            if rect.collidepoint(e.pos):
                                self._button_press(lbl)
                                break

    def _textinput(self, text):
        """Getypte tekens via pygame TEXTINPUT (betrouwbaarder dan KEYDOWN.unicode)."""
        if not text or self.in_settings or self.show_help:
            return
        if self.in_memory:
            self.mem_instr += text
            return
        if self.asking_name:
            self.name_text += text
            return
        if self.typing:
            self.type_text += text
            return
        # buiten een veld: het eerste teken opent meteen de typbalk
        # (spatie negeren: dat is push-to-talk)
        if not self.busy and text.strip():
            self.typing = True
            self.type_text = text

    def _keydown(self, e):
        # snelgids-overlay heeft voorrang
        if e.key == pygame.K_F1:
            self.show_help = not self.show_help
            return
        if self.show_help:
            if e.key == pygame.K_ESCAPE:
                self.show_help = False
            return
        # stem-instellingen open?
        if self.in_settings:
            self._settings_key(e)
            return
        # geheugen-scherm open?
        if self.in_memory:
            self._memory_key(e)
            return
        # eerste keer: naam invoeren (tekens via _textinput)
        if self.asking_name:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._save_name()
            elif e.key == pygame.K_ESCAPE:
                self._save_name()   # leeg = zonder naam verder
            elif e.key == pygame.K_BACKSPACE:
                self.name_text = self.name_text[:-1]
            return
        if self.typing:
            if e.key == pygame.K_RETURN:
                if e.mod & pygame.KMOD_SHIFT:     # Shift+Enter = nieuwe regel
                    self.type_text += "\n"
                else:
                    self._send_typed()
            elif e.key == pygame.K_ESCAPE:
                self.typing = False
                self.type_text = ""
            elif e.key == pygame.K_BACKSPACE:
                self.type_text = self.type_text[:-1]
            return
        if e.key == pygame.K_ESCAPE:
            if self.pending:
                self.pending = None      # weer/nieuws-vraag annuleren
            else:
                self.running = False
        elif e.key == pygame.K_SPACE and not self.busy and self.ears.available():
            self._start_listening()
        elif e.key == pygame.K_F2:
            self.in_settings = True
            self.set_idx = 0
            self.voice.warmup()
        elif e.key == pygame.K_F3:
            self._open_memory()
        elif e.key == pygame.K_RETURN:
            self.typing = True
            self.type_text = ""

    def _start_listening(self):
        self.ears.start()
        if self.ears.recording():
            self.state = "listening"

    def _stop_listening(self):
        audio = self.ears.stop()
        self.busy = True
        self.state = "thinking"
        threading.Thread(target=self._handle_audio, args=(audio,), daemon=True).start()

    # ---------- niveau voor de balkjes ----------
    def _level(self, t):
        if self.state == "speaking":
            return self.voice.level()
        if self.state == "listening":
            return 0.28 + 0.18 * (0.5 + 0.5 * pygame_sin(t * 8))
        if self.state in ("thinking", "searching"):
            return 0.45 + 0.4 * abs(pygame_sin(t * 4))
        return 0.04 * max(0.0, pygame_sin(t * 1.5))  # rustige idle-flikker

    # ---------- tekenen ----------
    def draw(self, t):
        highlight = self.btn_flash if time.time() < self.btn_flash_until else None
        self.panel.draw(self.screen, self._level(t), self.state, t, highlight)
        if self.asking_name:
            self._name_prompt(t)
        elif self.in_settings:
            self._settings_panel(t)
        elif self.in_memory:
            self._memory_panel(t)
        else:
            self._status(t)
            self._util_buttons()
        if self.show_help:
            self._help_panel(t)

    def _util_buttons(self):
        """Altijd zichtbare knoppen linksboven (geen sneltoetsen nodig)."""
        s = self.screen
        self.util_hits = []
        items = [("Instellingen", "settings", GREEN), ("Geheugen", "memory", GREEN),
                 ("Snelgids", "help", AMBER), ("Doneren", "donate", GREEN)]
        y = 12
        for label, act, col in items:
            r = pygame.Rect(12, y, 128, 34)
            pygame.draw.rect(s, (24, 26, 30), r, border_radius=7)
            pygame.draw.rect(s, col, r, width=2, border_radius=7)
            self._blit_center(s, label, self.font_btn, (228, 228, 233), r)
            self.util_hits.append((act, r))
            y += 40

    def _util_click(self, pos):
        for act, rect in self.util_hits:
            if rect.collidepoint(pos):
                if act == "settings":
                    self.in_settings = True
                    self.set_idx = 0
                    self.voice.warmup()
                elif act == "memory":
                    self._open_memory()
                elif act == "help":
                    self.show_help = True
                elif act == "donate":
                    try:
                        webbrowser.open(DONATE_URL)
                    except Exception:
                        pass
                return True
        return False

    def _settings_panel(self, t):
        s = self.screen
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 205))
        s.blit(ov, (0, 0))
        self._center(s, "Instellingen", self.font_l, GREEN, 64)
        sname = {1.0: "Normaal", 1.25: "Groot",
                 1.5: "Extra groot"}.get(round(self.ui_scale, 2),
                                         "%d%%" % int(self.ui_scale * 100))
        rows = [
            ("Stem", self.voice.voice or "?"),
            ("Snelheid", "%.2f" % self.voice.speed),
            ("Toonhoogte", "%.2f" % self.voice.pitch),
            ("Volume", "%d%%" % int(self.voice.volume * 100)),
            ("Stem aan/uit", "aan" if self.voice.enabled else "uit"),
            ("Tekstgrootte", sname),
        ]
        self.set_hits = []      # (soort, index, delta, rect) voor muisklikken
        y = 130
        for i, (lab, val) in enumerate(rows):
            sel = (i == self.set_idx)
            col = GOLD if sel else (220, 220, 225)
            # < en > klikbare knopjes
            lrect = pygame.Rect(WIDTH // 2 - 250, y - 18, 38, 36)
            rrect = pygame.Rect(WIDTH // 2 + 212, y - 18, 38, 36)
            for rc, ch in ((lrect, "<"), (rrect, ">")):
                pygame.draw.rect(s, (46, 46, 54) if sel else (32, 32, 38), rc, border_radius=6)
                pygame.draw.rect(s, GREEN if sel else (70, 70, 78), rc, width=2, border_radius=6)
                self._blit_center(s, ch, self.font, (235, 235, 240), rc)
            if sel:
                row_bg = pygame.Rect(WIDTH // 2 - 205, y - 18, 410, 36)
                pygame.draw.rect(s, (30, 38, 30), row_bg, border_radius=6)
            self._center(s, "%s:  %s" % (lab, val), self.font, col, y)
            self.set_hits.append(("adj", i, -1, lrect))
            self.set_hits.append(("adj", i, 1, rrect))
            self.set_hits.append(("sel", i, 0, pygame.Rect(WIDTH // 2 - 205, y - 18, 410, 36)))
            y += 52
        if not self.voice.list_voices():
            self._center(s, "(stemmenlijst laadt nog...)", self.font_s, MUTE, y)
            y += 24
        # Test- en Sluit-knoppen (klikbaar)
        test_rect = pygame.Rect(WIDTH // 2 - 170, y + 14, 160, 42)
        close_rect = pygame.Rect(WIDTH // 2 + 10, y + 14, 160, 42)
        for rc, lbl, kindcol in ((test_rect, "Test stem", AMBER), (close_rect, "Sluiten", GREEN)):
            pygame.draw.rect(s, (28, 28, 34), rc, border_radius=8)
            pygame.draw.rect(s, kindcol, rc, width=2, border_radius=8)
            self._blit_center(s, lbl, self.font_s, (235, 235, 240), rc)
        self.set_hits.append(("test", 0, 0, test_rect))
        self.set_hits.append(("close", 0, 0, close_rect))
        self._center(s, "Klik op < / > of gebruik de pijltjestoetsen",
                     self.font_s, MUTE, y + 76)

    def _name_prompt(self, t):
        s = self.screen
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        s.blit(ov, (0, 0))
        self._center(s, "Hoe mag ik je noemen?", self.font_l, GREEN, HEIGHT // 2 - 70)
        box = pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 20, 440, 48)
        pygame.draw.rect(s, (20, 20, 24), box, border_radius=8)
        pygame.draw.rect(s, GREEN, box, width=2, border_radius=8)
        cur = self.name_text + ("_" if (t % 1.0) < 0.5 else "")
        self._center(s, cur or " ", self.font, (230, 230, 235), box.centery)
        self._center(s, "Enter = bevestigen  -  Esc = zonder naam", self.font_s, MUTE, HEIGHT // 2 + 50)

    def _center(self, surf, txt, font, color, y):
        img = font.render(txt, True, color)
        surf.blit(img, img.get_rect(center=(WIDTH // 2, y)))

    def _blit_center(self, surf, txt, font, color, rect):
        img = font.render(txt, True, color)
        surf.blit(img, img.get_rect(center=rect.center))

    def _status(self, t):
        s = self.screen
        idle_lbl = ("SPATIE = praten of typ je vraag (Enter). Knoppen linksboven: "
                    "stem, geheugen, gids."
                    if self.ears.available() else
                    "Typ je vraag (Enter). Knoppen linksboven: stem, geheugen, gids.")
        if self.pending == "weather":
            idle_lbl = "Welke stad? Typ het of houd SPATIE in om te spreken."
        elif self.pending == "news":
            idle_lbl = "Welke nieuwsbron? Typ het of houd SPATIE in om te spreken."
        labels = {"idle": idle_lbl,
                  "listening": "Luisteren...", "thinking": "Denken...",
                  "searching": "Online zoeken...", "speaking": "Spreken..."}
        col = {"idle": MUTE, "listening": GREEN, "thinking": AMBER,
               "searching": AMBER, "speaking": SEG_ON}[self.state]
        if self.pending and self.state == "idle":
            col = GREEN
        img = self.font.render(labels[self.state], True, col)
        s.blit(img, (20, HEIGHT - 96))
        # laatste vraag/antwoord
        if self.last_user:
            self._wrap(s, "Jij: " + self.last_user, MUTE, 20, HEIGHT - 70, WIDTH - 40, self.font_s)
        if self.last_reply:
            self._wrap(s, "KITT: " + self.last_reply, (210, 210, 215), 20, HEIGHT - 48, WIDTH - 40, self.font_s)
        # model laden/downloaden (afhankelijk van of het bestand er al is)
        if self.loading:
            self.model_btn_rect = None
            self._center(s, self.load_msg, self.font, AMBER, 40)
        elif self.need_model and not self.asking_name:
            self._draw_model_consent(s)
        else:
            self.model_btn_rect = None
        # beschikbaarheid + typhint rechtsonder
        hints = []
        if not self.ears.available():
            hints.append("geen microfoon - typ je vraag")
        if self.brain.local is not None:
            if not self.loading and self.ollama_ok is False:
                hints.append("model niet beschikbaar (zie README)")
        elif self.ollama_ok is False:
            hints.append("Ollama offline")
        if hints:
            h = self.font_s.render(" | ".join(hints), True, (200, 90, 70))
            s.blit(h, h.get_rect(bottomright=(WIDTH - 16, HEIGHT - 8)))
        # typ-balk (groot, meerregelig; Shift+Enter = nieuwe regel)
        if self.typing:
            line_h = self.font_in.get_height() + 2
            bh = line_h * 3 + 14
            box = pygame.Rect(20, HEIGHT - bh - 14, WIDTH - 40, bh)
            pygame.draw.rect(s, (20, 20, 24), box, border_radius=8)
            pygame.draw.rect(s, GREEN, box, width=2, border_radius=8)
            prefix = {"weather": "Stad: ", "news": "Bron: "}.get(self.pending, "Typ: ")
            lines = self._wrap_lines(prefix + self.type_text, self.font_in, box.w - 16)
            if (t % 1.0) < 0.5:
                lines[-1] = lines[-1] + "|"
            for i, ln in enumerate(lines[-3:]):
                s.blit(self.font_in.render(ln, True, (220, 220, 225)),
                       (box.x + 8, box.y + 7 + i * line_h))

    def _wrap(self, surf, text, color, x, y, maxw, font):
        words = text.split(" ")
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] > maxw and line:
                surf.blit(font.render(line, True, color), (x, y))
                return  # 1 regel; rest afkappen om de HUD klein te houden
            line = test
        surf.blit(font.render(line, True, color), (x, y))

    def _wrap_lines(self, text, font, maxw):
        """Breek tekst af in een lijst regels (respecteert ook echte \\n)."""
        out = []
        for para in text.split("\n"):
            words = para.split(" ")
            line = ""
            for w in words:
                test = (line + " " + w).strip()
                if line and font.size(test)[0] > maxw:
                    out.append(line)
                    line = w
                else:
                    line = test
            out.append(line)
        return out

    def run(self):
        try:
            while self.running:
                self.clock.tick(FPS)
                t = pygame.time.get_ticks() / 1000.0
                self.handle_events()
                self.draw(t)
                pygame.display.flip()
        finally:
            self.shutdown()

    def shutdown(self):
        """Netjes afsluiten: stem stoppen, Ollama afsluiten (als wij hem startten),
        geheugen sluiten."""
        try:
            self.voice.stop()
        except Exception:
            pass
        try:
            self.brain.shutdown()
        except Exception:
            pass
        try:
            self.memory.close()
        except Exception:
            pass


def pygame_sin(x):
    import math
    return math.sin(x)


def main():
    try:  # Dravenlock: stille update-check (uit te zetten in de melding)
        import drave_update
        drave_update.start(None, 'DraveKITT', '1.0.1')
    except Exception:
        pass
    pygame.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("DraveKITT")
    import splash
    splash.set_window_icon()
    pygame.key.set_repeat(350, 60)   # ingedrukt houden = herhalen (handig in menu's)
    try:
        pygame.key.start_text_input()
    except Exception:
        pass
    app = App(screen)
    # splashscherm met logo tot de stem + het model klaar zijn (bij de eerste keer,
    # als we nog om de naam vragen, meteen door naar de app)
    splash.run_splash(
        screen, app.clock, "DraveKITT",
        status_fn=lambda: (app.load_msg if app.loading else "Opstarten"),
        is_ready=lambda: app.asking_name or app.ready)
    app.run()
    pygame.quit()


if __name__ == "__main__":
    main()
