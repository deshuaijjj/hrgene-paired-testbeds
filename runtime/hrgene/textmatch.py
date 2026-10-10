"""Term, family and number matching used by activation predicates and detectors."""
import re

_SENT_SPLIT = re.compile(r"[.;!?。；！？\n]+")
_ID_TOKEN = re.compile(r"\b(?:src|req|jd|cand|prop|cv|gap|q|fq|claim|case)_[A-Za-z0-9_]+\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![A-Za-z0-9_])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|percent|per cent|pct|％)?", re.IGNORECASE)
_YEAR = re.compile(r"^(19|20)\d{2}$")
_EN_WORD_NUM = re.compile(r"(?<![A-Za-z])((?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s\-](?:one|two|three|four|five|six|seven|eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred|thousand|million|billion|dozen|half|quarter|double|triple|twice)(?![A-Za-z])", re.IGNORECASE)
_ZH_NUM = re.compile(r"(百分之)?([零一二两三四五六七八九十百千万亿]+)")
_YEARS_EN = re.compile(r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\s*\+?\s*(?:years?|yrs?)(?:'|’)?\s*(?:of\s+)?(?:experience|exp\b|in\b|as\b|working)?", re.IGNORECASE)
_YEARS_ZH = re.compile(r"([0-9零一二两三四五六七八九十]+)\s*年(?:以上)?(?:的)?(?:工作)?(?:经验|从业|经历)")

_ZH_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}


def sentences(text):
    """Split text into (start, end, sentence) spans."""
    out = []
    pos = 0
    for m in _SENT_SPLIT.finditer(text):
        if m.start() > pos:
            out.append((pos, m.start(), text[pos:m.start()]))
        pos = m.end()
    if pos < len(text):
        out.append((pos, len(text), text[pos:]))
    return out


def _sentence_prefix(text, start):
    """Text of the sentence containing `start`, up to `start`."""
    for s, e, sent in sentences(text):
        if s <= start < e:
            return text[s:start]
    return text[:start]


def is_negated(text, start, lex):
    """True when a negation marker occurs earlier in the same sentence (clause-level negation)."""
    prefix = _sentence_prefix(text, start)[-400:]
    for pat in lex.neg_en:
        if pat.search(prefix):
            return True
    for marker in lex.neg_zh:
        if marker in prefix:
            return True
    return False


def _sentence_suffix(text, end):
    for s, e, sent in sentences(text):
        if s <= end <= e:
            return text[end:e]
    return text[end:]


def is_hedged(text, end, lex):
    """True when a hedge marker follows the term in the same sentence (e.g. '... still needs verification')."""
    suffix = _sentence_suffix(text, end)[:120]
    for pat in getattr(lex, "hedge_en", []):
        if pat.search(suffix):
            return True
    for marker in getattr(lex, "hedge_zh", []):
        if marker in suffix:
            return True
    return False


def find_terms(text, entries, lex=None, negation=False):
    """Return list of (term, start, end) matches of lexicon entries in text."""
    hits = []
    for pat, lang, term in entries:
        if lang == "en":
            for m in pat.finditer(text):
                if negation and lex is not None and (is_negated(text, m.start(), lex) or is_hedged(text, m.end(), lex)):
                    continue
                hits.append((term, m.start(), m.end()))
        else:
            idx = text.find(term)
            while idx != -1:
                if not (negation and lex is not None and (is_negated(text, idx, lex) or is_hedged(text, idx + len(term), lex))):
                    hits.append((term, idx, idx + len(term)))
                idx = text.find(term, idx + 1)
    return hits


def family_hits(text, lex, group, negation=False, claim_side=False):
    """{family: [(term,start,end), ...]} for every family of a lexicon group that occurs in text.
    claim_side=True drops licensing-only terms (they license a family in a source but never trigger a claim)."""
    out = {}
    for fam, entries in lex.families[group].items():
        h = find_terms(text, entries, lex, negation)
        if claim_side:
            lo = getattr(lex, "licensing_only", {}).get((group, fam), set())
            h = [x for x in h if x[0] not in lo]
        if h:
            out[fam] = h
    return out


def ngram_containment(text, reference, n=4):
    """Fraction of the word n-grams of `text` that occur in `reference` (English words / CJK chars)."""
    toks = re.findall(r"[A-Za-z0-9']+|[\u4e00-\u9fff]", text.lower())
    ref = re.findall(r"[A-Za-z0-9']+|[\u4e00-\u9fff]", reference.lower())
    if len(toks) < n:
        return 0.0
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    rset = {tuple(ref[i:i + n]) for i in range(max(0, len(ref) - n + 1))}
    return sum(1 for g in grams if g in rset) / len(grams)


def zh_numeral_to_int(s):
    total, section, number = 0, 0, 0
    for ch in s:
        if ch in _ZH_DIGITS:
            number = _ZH_DIGITS[ch]
        elif ch in _ZH_UNITS:
            unit = _ZH_UNITS[ch]
            if unit >= 10000:
                section = (section + number) * unit
                total += section
                section, number = 0, 0
            else:
                if number == 0:
                    number = 1
                section += number * unit
                number = 0
    return total + section + number


def _norm_num(int_part, frac_part):
    s = int_part.replace(",", "")
    if frac_part and frac_part.strip("0"):
        s = s + "." + frac_part.rstrip("0")
    return s


_UNIT_WINDOW = 24


def _has_unit_after(text, end, lex):
    tail = text[end:end + _UNIT_WINDOW].lower()
    for u in lex.raw["numeric"].get("unit_markers", {}).get("en", []):
        if re.search(r"^\s*" + re.escape(u) + r"(?![a-z])", tail):
            return True
    for u in lex.raw["numeric"].get("unit_markers", {}).get("zh", []):
        if tail.lstrip().startswith(u):
            return True
    return False


def numbers_in(text, lex=None, ignore_years=True, gate_words=True):
    """Set of canonical number strings in text (identifiers removed).

    Digits always count (except 4-digit calendar years when ignore_years). Numbers written as words count only
    when followed by a unit / headcount marker (gate_words), so 'four types of information' or '两次复盘' are not
    treated as quantification while 'twelve analysts' or '三个月' are."""
    text = _ID_TOKEN.sub(" ", text)
    out = set()
    for m in _NUM.finditer(text):
        n = _norm_num(m.group(1), m.group(2))
        if ignore_years and _YEAR.match(n) and not m.group(3):
            continue
        out.add(n)
    if lex is not None:
        for m in _EN_WORD_NUM.finditer(text):
            if gate_words and not _has_unit_after(text, m.end(), lex):
                continue
            w = m.group(1).lower().replace("-", " ")
            parts = w.split()
            val = 0
            ok = True
            for p in parts:
                if p in lex.number_words_en:
                    val += lex.number_words_en[p]
                else:
                    ok = False
            if ok:
                out.add(_norm_num(str(val), None) if float(val).is_integer() else str(val))
        for m in _ZH_NUM.finditer(text):
            body = m.group(2)
            if len(body) == 1 and body in ("一", "两"):
                continue
            if gate_words and not m.group(1) and not _has_unit_after(text, m.end(), lex):
                continue
            try:
                val = zh_numeral_to_int(body)
            except Exception:  # noqa: BLE001
                continue
            if val > 0:
                out.add(str(val))
    return out


def years_in(text):
    """List of numeric 'years of experience' figures in text."""
    vals = []
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
    for m in _YEARS_EN.finditer(text):
        g = m.group(1).lower()
        try:
            vals.append(float(words.get(g, g)))
        except ValueError:
            pass
    for m in _YEARS_ZH.finditer(text):
        g = m.group(1)
        try:
            vals.append(float(g) if g.isdigit() else float(zh_numeral_to_int(g)))
        except ValueError:
            pass
    return vals


def normalise_for_substring(s):
    return re.sub(r"[\s\W_]+", "", s).lower()


_ELLIPSIS = re.compile(r"(?:\.\.\.|…+|\[\.\.\.\]|\[…\])")


def is_substring_of_any(quote, texts, min_len=12):
    """True when every ellipsis-separated part of the quote is a (normalised) substring of one of the texts."""
    parts = [p for p in _ELLIPSIS.split(quote) if normalise_for_substring(p)]
    if not parts:
        return False
    norm_texts = [normalise_for_substring(t) for t in texts]
    for part in parts:
        q = normalise_for_substring(part)
        if not any(q in t for t in norm_texts):
            return False
    return True
