# Test van KITT's nieuwe motor (Claudio, 19 okt 2026) - verandert niets
import os, time
from localbrain import LocalBackend
from llamaapp import LlamaAppBackend
data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DraveKITT-data")
eigen = LocalBackend("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf", data)
b = LlamaAppBackend(terugval=eigen)
t = time.time(); print("klaar:", b.ensure(), "| motor:", b.naam(), "| %.1fs" % (time.time() - t))
t = time.time()
print("ANTWOORD:", b.chat([{"role": "system", "content": "Je bent KITT, een pratende auto. Antwoord kort in het Nederlands."},
                           {"role": "user", "content": "Hallo KITT, hoe gaat het met je?"}]))
print("motor na antwoord:", b.naam(), "| %.1fs" % (time.time() - t))
