# -*- coding: utf-8 -*-
"""brain.py - het 'brein' van KITT via een lokaal Ollama-model.

Naast chatten kan dit brein:
  * Ollama automatisch starten (ollama serve) als die nog niet draait, en hem
    weer afsluiten bij het sluiten van de app (alleen als wij hem startten).
  * Relevante herinneringen uit het geheugen meenemen in de context.
  * Online zoeken: het model mag antwoorden met één regel 'ZOEK: <term>'; dan
    voert de app de zoekopdracht uit en vraagt om een definitief antwoord.

Alles via urllib uit de standaardbibliotheek; geen externe pakketten nodig.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.request

DEFAULT_SYSTEM = (
    "Je bent KITT, een geavanceerde AI-assistent ingebouwd in een auto, in de "
    "stijl van een pratende, slimme wagen. Je bent kalm, gevat, loyaal en "
    "behulpzaam, en spreekt de bestuurder direct aan. Geeft de bestuurder je een "
    "andere naam, gebruik die dan voortaan (ook bij 'hoe heet jij'). Antwoord kort "
    "en gesproken (1 tot 3 zinnen), in het Nederlands, zonder opsommingen of "
    "opmaak.\nJe hebt een geheugen van eerdere gesprekken; gebruik de herinneringen "
    "en feiten uit de context. Krijg je zoekresultaten mee, gebruik die en geef "
    "meteen het antwoord - zeg NOOIT dat je iets gaat opzoeken; geef direct "
    "antwoord."
)

# Identiteits-/geheugenvragen: nooit online zoeken.
_NO_SEARCH = ("heet", "naam", "wie ben", "noem ik", "noem je", "wat zei",
              "herinner", "onthoud", "geheugen", "wie bent")

# Korte 'feiten-extractor' om na een gesprek een blijvend weetje op te slaan.
FACT_SYSTEM = (
    "Haal uit het bericht van de bestuurder maximaal één kort, blijvend, "
    "persoonlijk feit (naam, voorkeur, bezit, afspraak, belangrijke datum). "
    "Antwoord met alleen dat ene feit in één korte zin, of met alleen 'GEEN' "
    "als er geen blijvend feit in staat."
)

# Zinnen waarmee de bestuurder expliciet iets laat onthouden.
REMEMBER_TRIGGERS = (
    "onthoud dat ", "onthoud dit ", "onthoud even dat ", "onthoud even ",
    "onthoud dit:", "onthoud:", "remember that ", "remember this ", "remember:",
)

# Aparte 'router' die alleen beslist of er online gezocht moet worden.
ROUTER_SYSTEM = (
    "Je bepaalt of er online opgezocht moet worden om de vraag goed te "
    "beantwoorden. Antwoord met PRECIES één regel: 'NEE' als je het uit eigen "
    "kennis kunt beantwoorden, of 'ZOEK: <zoekterm>' als er actuele of feitelijke "
    "informatie nodig is (zoals weer, nieuws, sport, prijzen, datums of recente "
    "gebeurtenissen). Geef geen verdere uitleg."
)


class Brain:
    def __init__(self, host="http://localhost:11434", model="llama3.2",
                 system=None, history_len=12, timeout=120):
        self.host = host.rstrip("/")
        self.model = model
        self.system = system or DEFAULT_SYSTEM
        self.history = []
        self.history_len = history_len
        self.timeout = timeout
        self.last_error = None
        self.memory = None          # optioneel: memory.Memory
        self.search = None          # optioneel: search.Search
        self.user_name = ""         # naam van de bestuurder (KITT spreekt zo aan)
        self.assistant_name = ""    # door de bestuurder gegeven naam (blijft bewaard)
        self.instructions = ""      # vaste richtlijnen (Geheugen)
        self.stop_ollama_on_exit = False  # ook een al-draaiende Ollama stoppen?
        self.local = None           # localbrain.LocalBackend (in-app model, geen Ollama)
        self.auto_learn = True      # na elk gesprek zelf een blijvend feit opslaan
        self._proc = None           # door ons gestart 'ollama serve'

    # ---------- backend (lokaal model of Ollama) ----------
    def reachable(self):
        if self.local is not None:
            return self.local.available()
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=4) as r:
                json.loads(r.read().decode("utf-8"))
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def ensure_running(self, wait=15):
        """Zorg dat het brein klaar is. Lokaal: model laden. Anders: Ollama starten."""
        if self.local is not None:
            return self.local.ensure()
        if self.reachable():
            return True
        try:
            kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            self._proc = subprocess.Popen(["ollama", "serve"], **kwargs)
        except Exception as e:
            self.last_error = "kon ollama niet starten: %s" % e
            return False
        t0 = time.time()
        while time.time() - t0 < wait:
            if self.reachable():
                return True
            time.sleep(0.8)
        return self.reachable()

    def _kill_tree(self, proc):
        """Beëindig een proces én zijn child-processen (de echte server)."""
        if proc is None:
            return
        pid = proc.pid
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        except Exception:
            pass
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def shutdown(self):
        """Sluit Ollama af bij het sluiten van de app.

        Standaard alleen de Ollama die wij zelf startten. Staat
        stop_ollama_on_exit aan, dan wordt ook een al-draaiende Ollama gestopt.
        Bij een lokaal model is er niets af te sluiten.
        """
        if self.local is not None:
            self.local.close()
            return
        self._kill_tree(self._proc)
        self._proc = None
        if self.stop_ollama_on_exit:
            try:
                if os.name == "nt":
                    for img in ("ollama.exe", "ollama app.exe", "ollama_llama_server.exe"):
                        subprocess.run(["taskkill", "/F", "/IM", img],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(["pkill", "-f", "ollama"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def models(self):
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=4) as r:
                data = json.loads(r.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            self.last_error = str(e)
            return []

    # ---------- laag niveau: één chat-aanroep ----------
    def _post(self, messages):
        if self.local is not None:
            return self.local.chat(messages)
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": 0.7}}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/chat", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
        reply = (out.get("message", {}) or {}).get("content", "").strip()
        if not reply:
            reply = out.get("response", "").strip()
        return reply

    def _should_search(self, user_text):
        """Aparte router-aanroep: bepaalt of (en waarop) er gezocht moet worden.
        Geeft de zoekterm terug, of None."""
        if self.search is None:
            return None
        low = user_text.lower()
        if any(k in low for k in _NO_SEARCH):
            return None        # identiteits-/geheugenvraag: niet online zoeken
        try:
            route = self._post([{"role": "system", "content": ROUTER_SYSTEM},
                                {"role": "user", "content": user_text}])
        except Exception:
            return None
        line = (route or "").strip()
        if line.upper().startswith("ZOEK:"):
            q = line.split(":", 1)[1].strip()
            return q or user_text
        return None

    # ---------- naam/hernoemen herkennen ----------
    _RENAME_PATS = (
        r"ik noem je\s+([a-zA-Z][\w-]{1,20})",
        r"noem ik je\s+([a-zA-Z][\w-]{1,20})",
        r"(?:je|jij|jouw)\s+naam\s+is\s+([a-zA-Z][\w-]{1,20})",
        r"(?:je|jij)\s+heet\s+(?:nu\s+|voortaan\s+)?([a-zA-Z][\w-]{1,20})",
        r"heet\s+(?:je|jij)\s+(?:nu\s+|voortaan\s+)?([a-zA-Z][\w-]{1,20})",
        r"heet\s+nu\s+([a-zA-Z][\w-]{1,20})",
        r"(?:vanaf nu|voortaan)\s+heet\s+je\s+([a-zA-Z][\w-]{1,20})",
    )
    _RENAME_BAD = {"nu", "je", "jij", "jou", "jouw", "niet", "ook", "een", "de",
                   "het", "hoe", "wat", "wie", "oke", "oké", "ja", "nee",
                   "voortaan", "naam", "heet"}

    _USERNAME_PATS = (
        r"ik heet\s+([a-zA-Z][\w-]{1,20})",
        r"mijn naam is\s+([a-zA-Z][\w-]{1,20})",
        r"noem (?:mij|me)\s+([a-zA-Z][\w-]{1,20})",
    )
    _BAD_NAMES = {"moe", "blij", "klaar", "benieuwd", "boos", "ziek", "thuis",
                  "weg", "er", "het", "een", "aan", "oke", "oké"}

    def _detect_rename(self, text):
        """Nieuwe naam voor KITT zelf ('ik noem je X' / 'je heet nu X')."""
        low = text.lower()
        for p in self._RENAME_PATS:
            m = re.search(p, low)
            if m:
                name = m.group(1)
                if name not in self._RENAME_BAD and len(name) >= 2:
                    return name[:1].upper() + name[1:]
        return None

    def _detect_user_name(self, text):
        """Naam van de bestuurder ('ik heet X' / 'mijn naam is X' / 'ik ben Naam')."""
        low = text.lower()
        for p in self._USERNAME_PATS:
            m = re.search(p, low)
            if m:
                name = m.group(1)
                if (name not in self._RENAME_BAD and name not in self._BAD_NAMES
                        and len(name) >= 2):
                    return name[:1].upper() + name[1:]
        m = re.search(r"\bik ben\s+([A-Za-z][\w-]{1,20})", text)
        if m:
            name = m.group(1)
            if name[:1].isupper() and name.lower() not in self._BAD_NAMES:
                return name
        return None

    def _try_remember(self, user_text):
        """Expliciet 'onthoud (dit/dat/even) ...' -> sla op als feit. Geeft een
        bevestiging terug, of None als het geen onthoud-opdracht is."""
        low = user_text.lower()
        fact = None
        # 1) trigger aan het begin van de zin
        for trig in REMEMBER_TRIGGERS:
            if low.startswith(trig):
                fact = user_text[len(trig):].strip(" :")
                break
        # 2) 'onthoud dit/dat/even' of 'remember this/that' ERGENS in de zin
        if fact is None and re.search(r"(onthoud (dit|dat|even)|remember (this|that))", low):
            fact = re.sub(r"(?i)\s*\b(onthoud (dit|dat|even)?|remember (this|that)?)\b\s*[:,\.]?",
                          " ", user_text).strip(" ,.:")
        # 3) los 'onthoud ...' aan het begin (maar geen vraag als 'onthoud jij...')
        if fact is None and low.startswith("onthoud ") and not low.startswith(
                ("onthoud jij", "onthoud je", "onthoud jullie", "onthoud u ")):
            fact = user_text[len("onthoud "):].strip(" :")
        if not fact:
            return None
        if self.memory is not None:
            self.memory.remember_fact(fact)
        naam = (", " + self.user_name) if self.user_name else ""
        return "Genoteerd%s. Ik zal het onthouden." % naam

    def _extract_fact(self, user_text):
        """Achtergrond: laat het model een blijvend feit halen en sla het op."""
        try:
            out = self._post([{"role": "system", "content": FACT_SYSTEM},
                              {"role": "user", "content": user_text}])
            fact = (out or "").strip()
            if fact and fact.upper() != "GEEN" and len(fact) < 200 and self.memory is not None:
                self.memory.remember_fact(fact)
        except Exception:
            pass

    # ---------- hoog niveau: vraag beantwoorden ----------
    def ask(self, user_text, on_status=None):
        user_text = (user_text or "").strip()
        if not user_text:
            return ""
        # hernoemen van KITT (blijft bewaard)
        new_name = self._detect_rename(user_text)
        if new_name:
            self.assistant_name = new_name
            if self.memory is not None:
                self.memory.set_meta("assistant_name", new_name)
                self.memory.remember_fact("Jij (KITT) heet voortaan %s." % new_name)
            naam = (", " + self.user_name) if self.user_name else ""
            return "Begrepen%s, vanaf nu heet ik %s." % (naam, new_name)
        # naam van de bestuurder onthouden
        uname = self._detect_user_name(user_text)
        if uname:
            self.user_name = uname
            if self.memory is not None:
                self.memory.set_meta("user_name", uname)
                self.memory.remember_fact("De bestuurder heet %s." % uname)
            return "Aangenaam, %s. Ik onthoud je naam." % uname
        # expliciet onthouden gaat voor (geen model/zoekopdracht nodig)
        conf = self._try_remember(user_text)
        if conf is not None:
            return conf
        try:
            # 1) router beslist of er online gezocht moet worden
            results = ""
            q = self._should_search(user_text)
            if q:
                if on_status:
                    on_status("searching")
                try:
                    results = self.search.search(q)
                except Exception:
                    results = ""
                if on_status:
                    on_status("thinking")
            # 2) context opbouwen (vaste feiten + relevante herinneringen)
            ctx = ""
            if self.memory is not None:
                try:
                    facts = (self.memory.facts_voor(user_text, 6) if hasattr(self.memory, "facts_voor")
                             else self.memory.recent_facts(6))
                except Exception:
                    facts = []
                try:
                    mems = self.memory.recall(user_text)
                except Exception:
                    mems = []
                combined = []
                for x in facts + mems:
                    if x and x not in combined:
                        combined.append(x)
                if combined:
                    ctx = ("Wat je je herinnert (gebruik dit als het relevant is):\n- "
                           + "\n- ".join(combined[:8]))
            name_line = ""
            if self.user_name:
                name_line += ("\n\nDe BESTUURDER (je gesprekspartner) heet %s. Vraagt "
                              "de bestuurder 'wat is mijn naam' of 'hoe heet ik', "
                              "antwoord dan met %s. Spreek hem of haar af en toe "
                              "natuurlijk aan met die naam." % (self.user_name, self.user_name))
            if self.assistant_name:
                name_line += ("\n\nJIJZELF heet %s. Vraagt iemand 'hoe heet jij', "
                              "antwoord met %s. Verwar je eigen naam niet met die van "
                              "de bestuurder." % (self.assistant_name, self.assistant_name))
            rules = ""
            if self.instructions.strip():
                rules = ("\n\nVASTE RICHTLIJNEN van de bestuurder (volg deze strikt):\n"
                         + self.instructions.strip())
            search_block = ""
            if results:
                search_block = ("\n\nActuele zoekresultaten (gebruik deze en geef "
                                "meteen antwoord):\n" + results)
            sys_prompt = (self.system + rules + name_line
                          + (("\n\n" + ctx) if ctx else "") + search_block)
            messages = ([{"role": "system", "content": sys_prompt}]
                        + self.history[-self.history_len:]
                        + [{"role": "user", "content": user_text}])
            # 3) het eigenlijke antwoord
            reply = self._post(messages)
            if not reply:
                raise ValueError("leeg antwoord")
            # vastleggen in geschiedenis + geheugen
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": reply})
            self.history = self.history[-self.history_len:]
            if self.memory is not None:
                self.memory.add("user", user_text)
                self.memory.add("assistant", reply)
                # op de achtergrond een blijvend feit destilleren en opslaan
                if self.auto_learn:
                    threading.Thread(target=self._extract_fact,
                                     args=(user_text,), daemon=True).start()
            self.last_error = None
            return reply
        except Exception as e:
            self.last_error = str(e)
            return ("Sorry, ik kan mijn brein op dit moment niet bereiken. "
                    "Draait de Llama-app, of staat mijn eigen model klaar?")

    def reset(self):
        self.history = []
