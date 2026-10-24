"""Common Russianisms/calques in `ua` strings and manuals."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
BAD = [r"являєт", r"на протязі", r"слідуюч", r"приймати участь", r"прийміть участь", r"в залежності від",
       r"співпада", r"получ", r"відмін(и|іт|ен)", r"\bлюб(ий|а|е|ої|ого)\b", r"по замовчуванню", r"нажм", r"нажат",
       r"\bвірн(ий|о|а)\b", r"в якості", r"\bданн?(ий|а|е|ої|ого|ому|их)\b", r"заключа", r"\bприймаєт", r"\bнаступаюч",
       r"\bміроприєм", r"\bпо крайній мірі", r"\bвідноситься\b", r"\bзадавати питання", r"\bприкладом\b",
       r"\bвиключ(іть|ити|ено|ення)", r"\bвключ(іть|ити|ено|ення|ає)", r"\bпідтвердіть\b" , r"\bзберегти зміни\b",
       r"\bспасиб", r"\bнеобхідн", r"\bпредмет", r"\bсьогоднішн", r"\bкращ(е|ий) всього", r"\bбільш(е)? всього",
       r"\bзаплатит", r"\bприходит", r"\bпо причині", r"\bпо питанн", r"\bрахуйте\b", r"\bпопробу", r"\bнемає можливості",
       r"\bпереключ", r"\bуказ", r"\bпід час того як", r"\bсамий\b", r"\bсамої\b", r"\bсамого\b", r"\bвидалено успішно",
       r"\bзабороня", r"\bнастройк", r"\bустройств", r"\bпристрій\b(?=.*система)", r"\bожидан", r"\bнаходит", r"\bнаходяч"]
RX = re.compile("|".join(f"(?:{b})" for b in BAD), re.I)
def items():
    for f in sorted((ROOT/"src"/"strings").rglob("*.json")):
        for k, e in json.loads(f.read_text()).items():
            if isinstance(e, dict):
                for kk in ("ua", "ua_long"):
                    if isinstance(e.get(kk), str): yield f, k, e[kk]
    for f in sorted((ROOT/"src"/"manuals").glob("*.json")):
        for k, e in json.loads(f.read_text()).items(): yield f, k, e["ua"]
for f, k, ua in items():
    t = re.sub(r"\{[^}|]*\|?|\}|-\n?", "", ua).replace("\n", " ")
    for m in RX.finditer(t):
        print(f"{m.group(0).lower():14} {f.relative_to(ROOT)}:{k}: …{t[max(0,m.start()-30):m.end()+30]}…")
