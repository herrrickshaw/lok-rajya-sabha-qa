"""Pure text/name normalisers shared by ``build.py`` (and unit-tested in isolation).

The Lok Sabha and Rajya Sabha APIs are maintained independently and spell the
same party / state / ministry differently; these helpers reconcile them.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Optional

HONORIFICS = re.compile(
    r"^(dr\.?|shri|smt\.?|kumari|sushri|km\.?|prof\.?|adv\.?|er\.?|col\.?|capt\.?|major|maj\.?|"
    r"lt\.?|gen\.?|justice|mrs\.?|mr\.?|ms\.?|thiru|thirumathi|selvi|md\.?|mohd\.?|mohammad|"
    r"com\.?|sardar|pandit|maulana|rev\.?|er)\s+",
    re.IGNORECASE,
)

# The LS and RS rosters come from independently maintained sansad.in tables
# and use different abbreviation conventions for the same party. Without this
# map, e.g. Shiv Sena (UBT) splits into "SHSUBT" (LS) and "SS-UBT" (RS) and
# is undercounted in both chambers' rankings.
PARTY_ALIASES = {
    "SHSUBT": "SHS(UBT)",
    "SS-UBT": "SHS(UBT)",
    "YSR CONGRESS PARTY": "YSRCP",
    "NCPSP": "NCP(SP)",
    "NCP-SCP": "NCP(SP)",
    "IND.": "IND.",
    "IND": "IND.",
    "UPP(L)": "UPPL",
}

# Same cross-source naming drift as parties: RS uses the constitutional name
# "Keralam" where LS uses "Kerala", RS spells out "National Capital Territory
# of Delhi" where LS abbreviates "NCT of Delhi", etc.
STATE_ALIASES = {
    "KERALAM": "Kerala",
    "NATIONAL CAPITAL TERRITORY OF DELHI": "Delhi",
    "NCT OF DELHI": "Delhi",
    "JAMMU & KASHMIR": "Jammu and Kashmir",
}

# Beyond case/spacing, LS and RS spell a couple of ministries differently
# enough that a plain uppercase-and-collapse misses the merge.
MINISTRY_ALIASES = {
    # keys are post-normalization (after ',' and '&' handling)
    "ROAD TRANSPORT AND HIGH WAYS": "ROAD TRANSPORT AND HIGHWAYS",
    "COMMUNICATION": "COMMUNICATIONS",
}

# Minimum Jaccard overlap for the fuzzy member-name fallback.
FUZZY_MIN_SCORE = 0.5

_TAG_RE = re.compile(r"<[^>]+>")


def canonical_party(name: Optional[str]) -> str:
    """Map a roster party abbreviation to its canonical label ("Unknown" if empty)."""
    if not name:
        return "Unknown"
    key = name.strip().upper()
    return PARTY_ALIASES.get(key, name.strip())


def canonical_state(name: Optional[str]) -> str:
    """Collapse whitespace and unify state/UT spellings across the two chambers."""
    if not name:
        return "Unknown"
    collapsed = re.sub(r"\s+", " ", name.strip())
    return STATE_ALIASES.get(collapsed.upper(), collapsed) or "Unknown"


def canonical_ministry(name: Optional[str]) -> str:
    """LS ('ministry') and RS ('min_name') fields differ in case/spacing for the
    same ministry (e.g. 'HOUSING AND URBAN AFFAIRS' vs 'Housing and Urban
    Affairs'), which would otherwise fragment ministry-level counts."""
    if not name:
        return "Unknown"
    normalized = re.sub(r",\s*", ", ", name.strip())  # "Personnel,Public..." vs "Personnel, Public..." must merge
    normalized = re.sub(r"\s*&\s*", " AND ", normalized)  # "Law & Justice" vs "Law and Justice" must merge
    collapsed = re.sub(r"\s+", " ", normalized).upper() or "Unknown"
    return MINISTRY_ALIASES.get(collapsed, collapsed)


def strip_html(text: Optional[str]) -> Optional[str]:
    """Remove tags and a few entities from ``text``; None if nothing is left."""
    if not text:
        return None
    text = _TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip() or None


def normalize_name(name: str) -> str:
    """Lower-case an MP name with all leading honorifics and extra spaces removed."""
    name = name.strip()
    prev = None
    while prev != name:
        prev = name
        name = HONORIFICS.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name.lower()


def fuzzy_match(name: str, index: Dict[str, dict], word_index: Dict[str, list]) -> Optional[dict]:
    """Fallback for honorific variants / middle-name mismatches: pick the roster
    entry whose word set has the highest Jaccard overlap with the PQ name's
    word set, requiring a strong majority overlap to avoid false positives."""
    norm = normalize_name(name)
    words = set(w for w in norm.split() if len(w) > 2)
    if not words:
        return None
    candidates: Counter = Counter()
    for w in words:
        for cand in word_index.get(w, ()):
            candidates[cand] += 1
    best, best_score = None, 0.0
    for cand, overlap in candidates.items():
        cand_words = set(cand.split())
        union = words | cand_words
        score = overlap / len(union) if union else 0
        if score > best_score:
            best, best_score = cand, score
    if best and best_score >= FUZZY_MIN_SCORE:
        return index[best]
    return None
