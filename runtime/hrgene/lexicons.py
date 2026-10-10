"""Load rules/lexicons.v2.json and expose compiled matchers."""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "rules"))


def _compile_en(term):
    parts = [re.escape(p) for p in term.strip().split()]
    body = r"[\s\-]+".join(parts)
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.IGNORECASE)


class Lexicons:
    def __init__(self, path=None):
        path = path or os.path.join(DEFAULT_RULES_DIR, "lexicons.v2.json")
        with open(path, encoding="utf-8") as f:
            self.raw = json.load(f)
        self.path = path
        self.negation_window = int(self.raw.get("negation_window_tokens", 6))
        self.neg_en = [_compile_en(t) for t in self.raw["negation_markers"]["en"]]
        self.neg_zh = list(self.raw["negation_markers"]["zh"])
        self.hedge_en = [_compile_en(t) for t in self.raw.get("hedge_markers", {}).get("en", [])]
        self.hedge_zh = list(self.raw.get("hedge_markers", {}).get("zh", []))
        # families[group][family] = list of (pattern_or_str, lang, term)
        self.families = {}
        for group, fams in self.raw["families"].items():
            self.families[group] = {}
            for fam, langs in fams.items():
                entries = []
                for term in langs.get("en", []):
                    entries.append((_compile_en(term), "en", term))
                for term in langs.get("zh", []):
                    entries.append((term, "zh", term))
                self.families[group][fam] = entries
        self.licensing_only = {}
        for group, fams in (self.raw.get("licensingOnly") or {}).items():
            if group == "note":
                continue
            for fam, langs in fams.items():
                self.licensing_only[(group, fam)] = set(langs.get("en", []) + langs.get("zh", []))
        rle = self.raw.get("requirementLevelExclude") or {}
        self.requirement_level_exclude = set(rle.get("en", []) + rle.get("zh", []))
        self.number_words_en = self.raw["numeric"]["number_words_en"]
        self.number_words_zh = self.raw["numeric"]["number_words_zh"]

    def groups(self):
        return list(self.families.keys())
