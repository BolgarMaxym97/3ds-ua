"""Build the notification table the HOME Menu code patch reads at runtime.

The built-in tips of the Notifications applet (`new_tips0`..`new_tips16` in `menu_msbt`)
are not rendered from romfs. The HOME Menu copies each one into the news module's NAND
savedata through `news:s AddNotification`, and that copy is frozen at delivery time - so a
tip delivered before the mod was installed keeps the text of the language the console ran
then, forever, no matter what LayeredFS serves. LayeredFS cannot reach it and neither can a
romfs replacement.

What is in reach is HOME Menu's own code. The patch walks the 100 notification slots, and
for a slot whose stored title is one of Nintendo's tip titles in the language this build
replaces it writes our Ukrainian text back through `news:s`. The stored text is byte-for-byte the MSBT text - the
tips carry no style tags - which is what makes matching on a hash of the title reliable.

Table layout, little-endian, four words per entry, terminated by a zero hash:

    +0x00  u32  hash of the original title as stored in the notification header
    +0x04  u32  address of the ASCII label of the body   ("new_tips3")
    +0x08  u32  address of the ASCII label of the title  ("new_tips3_title")
    +0x0C  u32  hash of the Ukrainian title this build ships

The second hash is a gate, not a key: the stub fetches the title through HOME Menu's own
message lookup, which answers in whatever language the console is set to, and writes
nothing unless the answer is the Ukrainian string this build shipped. A console running
the mod in another language therefore keeps its notifications untouched, and so does one
whose translation has moved on since the patch was built.

The addresses are filled in by tools/luma_hook.py, which lays the labels out inside the
same blob; this module only decides which tips take part and hashes their text.
"""

from __future__ import annotations

import re
import struct

# Field capacities in UTF-16 code units, one reserved for the terminator.
TITLE_LIMIT = 0x40 // 2 - 1
MESSAGE_LIMIT = 0x1780 // 2 - 1

LABEL_RE = re.compile(r"^new_tips(\d+)(_title)?$")


def hash_text(text: str) -> int:
    """h = h * 31 + unit over the UTF-16 code units, which is two ARM instructions.

    Only used to recognise a string the console already holds, so a short multiplicative
    hash is enough - build_table() proves the values it emits do not collide.
    """
    raw = text.encode("utf-16-le")
    value = 0
    for unit in struct.unpack(f"<{len(raw) // 2}H", raw):
        value = (value * 31 + unit) & 0xFFFFFFFF
    return value


def tip_number(label: str) -> int | None:
    match = LABEL_RE.match(label)
    return int(match.group(1)) if match else None


def build_table(
    russian: dict[str, str], ukrainian: dict[str, str]
) -> tuple[list[dict[str, int | str]], list[str]]:
    """-> ([{ru_hash, ua_hash, body_label, title_label}], log), one entry per tip.

    Both mappings are {label: text}: `russian` as Nintendo wrote it (that is what the
    console stored), `ukrainian` with homoglyphs already applied (that is what the console
    will answer with once the mod is installed).

    A tip takes part only when both its title and its body are translated - a half-translated
    entry would leave a Ukrainian title over a Russian body.
    """
    entries: list[dict[str, int | str]] = []
    log: list[str] = []
    seen: dict[int, str] = {}

    for label, ru_title in sorted(russian.items(), key=lambda kv: (tip_number(kv[0]) or 0, kv[0])):
        if not label.endswith("_title") or (number := tip_number(label)) is None:
            continue
        body_label = f"new_tips{number}"
        ua_title, ua_body = ukrainian.get(label), ukrainian.get(body_label)
        if not ua_title or not ua_body:
            continue

        # The console stored what AddNotification accepted, so a Russian title that does not
        # fit the header field was truncated and its hash would never match.
        for what, text, limit in (
            (f"{label} (Russian)", ru_title, TITLE_LIMIT),
            (label, ua_title, TITLE_LIMIT),
            (body_label, ua_body, MESSAGE_LIMIT),
        ):
            if len(text) > limit:
                raise ValueError(f"{what} is {len(text)} code units, the field holds {limit}")

        ru_hash, ua_hash = hash_text(ru_title), hash_text(ua_title)
        if ru_hash == ua_hash:
            raise ValueError(f"{label}: the Russian and Ukrainian titles hash the same")
        if (clash := seen.get(ru_hash)) is not None:
            raise ValueError(f"{label} and {clash} have the same Russian title hash")
        seen[ru_hash] = label

        entries.append(
            {
                "number": number,
                "ru_hash": ru_hash,
                "ua_hash": ua_hash,
                "body_label": body_label,
                "title_label": label,
            }
        )
        log.append(f"{body_label}: {ua_title!r}, {len(ua_body)} code units")

    # A Ukrainian title hashing like any Russian one would make the stub match its own
    # output on the next pass, which is the one way this patch could loop.
    ua_hashes = {entry["ua_hash"] for entry in entries}
    if overlap := ua_hashes & set(seen):
        names = ", ".join(str(entry["title_label"]) for entry in entries if entry["ua_hash"] in overlap)
        raise ValueError(f"Ukrainian titles hash like Russian ones ({names}) - the stub would loop")

    return entries, log
