DraveKITT - een KITT-achtige voice box (Dravenlock Games)
=========================================================

Wat is het?
-----------
Een dashboard-paneel in de stijl van een pratende, slimme auto: drie kolommen
rode segmentbalkjes die meebewegen met de spraak, met een groene NORMAL-knop en
labelknoppen (ALT, OIL PRESS, OIL TEMP, EGT, FUEL / AUX, SAT COMM, ACC, RADAR,
MPI). Je praat met de auto-AI; het brein draait lokaal via Ollama, de stem via
neuvoice, en spraak-naar-tekst via Whisper.

Dit is een eigen interpretatie van de look-and-feel - geen echte Knight Rider-
audio of -logo's. Het is de voice box in het dashboard, NIET de scanner op de
motorkap.

Bediening
---------
- Houd SPATIE ingedrukt om te praten (push-to-talk), laat los en KITT antwoordt.
- Of typ gewoon je vraag (begin te typen of druk Enter) - ook handig zonder
  microfoon. Het typvak is groot en meerregelig: Enter = versturen,
  Shift+Enter = nieuwe regel, Esc = annuleren.
- Klik op de zijknoppen voor snelle functies (zie hieronder).
- Linksboven staan vier knoppen:
  * "Instellingen" - stem (stem, snelheid, toonhoogte, volume, aan/uit) EN
    Tekstgrootte (Normaal / Groot / Extra groot, voor grotere letters).
    Bedien met de muis (< / >, Test stem, Sluiten).
  * "Geheugen" - vaste richtlijnen schrijven + onthouden weetjes bekijken/
    verwijderen (zie 'Geheugen' hieronder).
  * "Snelgids" - korte uitleg van de bediening.
  * "Doneren" - opent PayPal (paypal.me/roger076). Contact: service@dravenlock.nl.
- Esc sluit het programma (of het open scherm).

De allereerste keer
-------------------
KITT vraagt hoe hij je mag noemen. Typ je naam en druk Enter (of Esc om het
zonder naam te doen). Hij onthoudt je naam en spreekt je er voortaan mee aan.
Daarna stelt KITT zich gesproken voor (in het Engels, de bekende KITT-intro).

De zijknoppen (tonen nu hun functie)
------------------------------------
Links:  TIJD = tijd & datum | ACCU = energie/accustatus | SYSTEEM = systeemcheck |
        GRAP = vertel een grap | WEER = het weer
Rechts: HERHAAL = herhaal laatste antwoord | NIEUWS = nieuws | NIEUW = nieuw
        gesprek (wist korte termijn) | SCAN = omgevingsscan | HULP = uitleg

WEER en NIEUWS vragen eerst om invoer: na het klikken typ je de stad
(bij WEER) of de nieuwsbron (bij NIEUWS) - OF je houdt SPATIE ingedrukt en
spreekt het in. Esc annuleert.
- WEER haalt nu de ECHTE actuele weergegevens op (via wttr.in, gratis, geen
  sleutel) en verzint dus niets meer - temperatuur, gevoelstemperatuur, wind en
  luchtvochtigheid. Vereist internet.
- NIEUWS gebruikt online zoeken + het taalmodel (kan minder exact zijn).

Snel starten (Windows)
----------------------
1. Dubbelklik op Start-DraveKITT.bat. Dit maakt eenmalig een omgeving aan en
   installeert de Python-pakketten (pygame, numpy, neuvoice, sounddevice,
   faster-whisper). De stem (neuvoice) en het Whisper-model downloaden zichzelf
   bij het eerste gebruik.
2. Zorg dat Ollama draait (zie hieronder) en start dan de voice box.

Een los programma maken (EXE)
-----------------------------
Dubbelklik op Maak-DraveKITT-EXE.bat. Die installeert alles en bouwt met
PyInstaller een map-versie in:  dist\DraveKITT\DraveKITT.exe
- Het is een MAP (onedir), geen los bestand: houd de hele map dist\DraveKITT
  bij elkaar. Je kunt die map verplaatsen/kopieren naar een andere pc.
- De stem, het Whisper- en het taalmodel zitten NIET in de build; die downloaden
  zichzelf bij de eerste start naar dist\DraveKITT\DraveKITT-data (eenmalig).
- Er is bewust een console-venster zichtbaar zodat je de download/voortgang ziet.
- Opnieuw beginnen? herstel.bat verwijdert .venv, build en dist (je instellingen
  en geheugen in DraveKITT-data blijven staan).
- Let op: het bundelen van llama-cpp / faster-whisper kan per pc nog een tweak
  vragen; lukt de build niet, deel dan de foutmelding.

Het brein: twee opties
----------------------
KITT kan zijn brein op twee manieren draaien (instelbaar met "backend" in
config.json):

A) "local" (STANDAARD - aanbevolen, geen Ollama nodig)
   Het model draait IN de app zelf via llama-cpp-python. Bij de eerste start
   wordt een klein modelbestand automatisch gedownload naar de data-map
   (DraveKITT-data\model\). Standaard: Qwen2.5-3B-Instruct (Q4_K_M, ~2,1 GB) -
   klein, snel en goed in Nederlands. Je hoeft Ollama dan NIET te installeren.
   - Wil je een ander/lichter model? Pas "local_repo" en "local_file" aan, bijv.
     een 2B-model. Het bestand komt in DraveKITT-data\model\.
   - De eerste keer duurt de download even (eenmalig). Daarna start het snel.
   - Lukt het installeren van llama-cpp-python niet (pip probeert te 'bouwen' en
     faalt)? Installeer dan de kant-en-klare wheel:
       pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
     (Start-DraveKITT.bat doet dit nu automatisch.) De exacte fout staat in
     DraveKITT-data\kitt-model-fout.txt.
   - Werkt het daarna nog niet? Schakel over op optie B (Ollama).

B) "ollama"
   Gebruikt een aparte Ollama-server. Zet "backend" op "ollama" in config.json.

Ollama installeren en een model draaien (alleen bij backend "ollama")
--------------------------------------------------------------------
1. Download en installeer Ollama van https://ollama.com (Windows/Mac/Linux).
2. Open een terminal en haal een model op, bijvoorbeeld:
       ollama pull llama3.2
   (Je kunt elk model gebruiken dat je zelf beheert; vul de naam in config.json
   in bij "model".)
3. KITT start Ollama nu ZELF als die nog niet draait (ollama serve), mits Ollama
   geinstalleerd is en in het PATH staat. Bij het sluiten van de app sluit KITT
   die Ollama ook weer af - maar alleen als KITT hem zelf gestart had. Draaide
   Ollama al (of als achtergronddienst), dan laat KITT hem met rust.
   Wil je dit niet, zet dan "autostart_ollama" op false in config.json.
4. KITT praat met Ollama op http://localhost:11434. Een ander adres? Pas
   "ollama_host" aan in config.json.

Nieuwe mogelijkheden
--------------------
- Begroeting: de allereerste keer stelt KITT zich gesproken voor. De tekst staat
  in config.json bij "greeting" - pas die gerust aan naar wat jij wilt. Wil je
  de begroeting opnieuw horen, zet dan "greeted" weer op false.
- Online zoeken: heeft KITT actuele info nodig, dan zoekt hij zelf op internet en
  vat de resultaten samen. Standaard via Startpage (privacyvriendelijk). Startpage
  heeft geen officiele API en blokkeert soms; lukt het niet, dan valt KITT
  automatisch terug op DuckDuckGo (pakket 'ddgs'). Kiezen met "search_engine":
  "startpage" of "duckduckgo". Uitzetten met "online_search": false.
- Geheugen: KITT onthoudt gesprekken in een lokale database
  (DraveKITT-data\kitt-geheugen.db) en haalt relevante dingen terug in latere
  gesprekken - zo "leert" hij je beter kennen. Alles blijft lokaal op je pc.
  Wil je het geheugen wissen: verwijder dat .db-bestand.
  * Zeg of typ "onthoud dat ..." (bijv. "onthoud dat mijn verjaardag 3 mei is")
    en KITT slaat dat als vast weetje op. Hij bevestigt met "Genoteerd".
  * Automatisch leren: na elk gesprek haalt KITT er zelf een blijvend weetje uit
    en bewaart dat. Uitzetten kan met "auto_learn": false in config.json.
  * Geheugen-scherm (F3): hier schrijf je VASTE RICHTLIJNEN - wat KITT wel/niet
    mag, je voorkeuren, gewenste stijl. Die volgt hij voortaan strikt en blijven
    bewaard. Je ziet er ook de onthouden weetjes: klik op de X om er een te
    verwijderen, of "Wis ALLE weetjes". "Opslaan & sluiten" bewaart je
    richtlijnen (Esc/F3 doet dat ook).
  * Hernoemen: zeg of typ "ik noem je X" of "je heet nu X" en KITT heet voortaan
    X (ook bij "hoe heet jij"); dat blijft bewaard, ook na herstart. Zeg "ik heet
    X" / "mijn naam is X" en KITT onthoudt jouw naam.

Instellingen (DraveKITT-data\config.json)
-----------------------------------------
Dit bestand wordt automatisch aangemaakt. Velden:
  "backend"      : "local" (model in de app, geen Ollama) of "ollama"
  "local_repo"   : Hugging Face-repo van het GGUF-model (backend local)
  "local_file"   : bestandsnaam van het GGUF-model (backend local)
  "model"        : naam van je Ollama-model (bij backend "ollama", bijv. "llama3.2")
  "ollama_host"  : adres van Ollama (standaard "http://localhost:11434")
  "voice_name"   : stemcode voor neuvoice ("M1" = man, "VYF1" = vrouw)
  "voice_speed"  : spreektempo (1.0 = normaal; ~0.6-1.6)
  "voice_pitch"  : toonhoogte (1.0 = normaal; ~0.8-1.3)
  "voice_volume" : volume 0.0-1.0
  "voice_on"     : stem aan/uit (true/false)
  (Deze vier kun je ook live aanpassen met F2 in de app.)
  "lang"         : taal, bijv. "nl"
  "whisper_size" : Whisper-model: "tiny", "base", "small", "medium"
                   (groter = nauwkeuriger maar langzamer)
  "autostart_ollama"    : true/false - Ollama zelf starten als die niet draait
  "stop_ollama_on_exit" : true/false - Ollama afsluiten als je KITT sluit (ook
                          een al-draaiende). Zet op false als je Ollama na het
                          sluiten wilt laten doordraaien.
  "online_search"    : true/false - mag KITT online zoeken
  "search_engine"    : "startpage" (privacy) of "duckduckgo"
  "auto_learn"       : true/false - na elk gesprek zelf een weetje opslaan
  "greeted"          : true/false - is de begroeting al geweest
  "greeting"         : de tekst die KITT de eerste keer uitspreekt ({name} wordt
                       vervangen door je naam)
  "user_name"        : je naam (KITT spreekt je hiermee aan; leeg = vraagt 'm)
  "instructions"     : vaste richtlijnen (ook te bewerken via F3 in de app)

Update je al eerder gedraaid? Verwijder DraveKITT-data\config.json voor een
schone start: dan vraagt KITT je naam opnieuw en hoor je de nieuwe (Engelse)
begroeting. Je geheugen (kitt-geheugen.db) blijft gewoon behouden.
De gevonden stemmen worden weggeschreven in DraveKITT-data\kitt-stemmen.txt.

Werkt iets niet?
----------------
- "Ollama offline" rechtsonder: Ollama draait niet of het adres klopt niet.
- "microfoon uit": geen microfoon/sounddevice of geen whisper -> druk T om te
  typen. Het dashboard en de stem werken dan nog steeds.
- Bij een crash staat de oorzaak in DraveKITT-data\kitt-fout.txt.

Tip
---
Het eerste antwoord kan even duren: het Whisper-model en de stem moeten dan nog
inladen. Daarna gaat het vlotter.
