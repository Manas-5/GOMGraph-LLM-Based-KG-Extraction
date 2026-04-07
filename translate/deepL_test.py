import deepl
import glob
import numpy as np
import json
import re   

MAX_BYTES = 100_000  

def utf8len(s: str) -> int:
    return len(s.encode("utf-8"))

def chunk_paragraphs(text: str, max_bytes=MAX_BYTES):
    # split on blank lines first; fall back to sentences if there are no blanks
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or re.split(r"(?<=[.!?])\s+", text)
    chunks, cur, cur_bytes = [], [], 0
    for p in paras:
        b = utf8len(p)
        if b > max_bytes:  # very long paragraph: hard-split by length
            start = 0
            buf = p
            while utf8len(buf) > max_bytes:
                # split at safe boundary within limit
                cut = max_bytes
                # walk back to a space if possible
                while cut > 0 and (start + cut) < len(p) and (p[start+cut] != ' '):
                    cut -= 1
                cut = cut or max_bytes
                segment = p[start:start+cut].strip()
                chunks.append(segment)
                start += cut
                buf = p[start:]
            if buf.strip():
                if cur_bytes + utf8len(buf) <= max_bytes:
                    cur.append(buf.strip()); cur_bytes += utf8len(buf)
                else:
                    if cur: chunks.append("\n\n".join(cur))
                    chunks.append(buf.strip())
                    cur, cur_bytes = [], 0
            continue
        if cur_bytes + b <= max_bytes:
            cur.append(p); cur_bytes += b
        else:
            chunks.append("\n\n".join(cur)); cur, cur_bytes = [p], b
    if cur: chunks.append("\n\n".join(cur))
    return chunks

def translate_large(text: str, target_lang="EN", **kwargs) -> str:
    parts = chunk_paragraphs(text)
    out = []
    for part in parts:
        res = translator.translate_text(part, target_lang=target_lang, **kwargs)
        out.append(res.text if hasattr(res, "text") else res[0].text)
    return "\n\n".join(out)

auth_key_pro = "88d93613-b671-4b31-8f47-bca88689d681"
auth_key = "c53357f6-a75e-4b54-83f2-d8f4f508ffc9:fx"

fs=glob.glob("../data/GOM_txt/*.txt")
fs.sort()
txts= []

for f in fs[3:]:
    print(f)
    with open(f, "r", encoding="utf-8") as file:
        txt = file.read()
        translator = deepl.Translator(auth_key_pro)
        #parts = chunk_paragraphs(txt)
         
        result = translate_large(txt, target_lang="EN-US")
        with open(f"../data/GOM_EN/{f.split('/')[-1].split('.')[0]}.txt", "w", encoding="utf-8") as wfile:
           wfile.write(result)
        

"""
translator = deepl.Translator(auth_key)

fs = glob.glob("../data/causality_frame_examples/FR/*.json")
for f in fs:
    exs = json.load(open(f))
    name = f.split("/")[-1].split(".")[0].split("_")[1]
    exs_tr = []
    for ex in exs[name]:
        ex_tr = translator.translate_text(ex["text"], source_lang="FR", target_lang="EN-US").text
        exs_tr.append(ex_tr)

    with open(f"../data/causality_frame_examples/EN/{name}.json", "w", encoding="utf-8") as f:
            json.dump(exs_tr, f, ensure_ascii=False, indent=4)
"""
