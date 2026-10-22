"""Title relevance, location and posting-text rules for Zaid's search."""
import re

GCC = re.compile(
    r"\b(uae|u\.a\.e|united arab emirates|dubai|abu dhabi|sharjah|ajman|ras al|fujairah|"
    r"saudi|ksa|riyadh|jeddah|jiddah|dammam|khobar|dhahran|neom|mecca|makkah|medina|"
    r"qatar|doha|bahrain|manama|kuwait|oman|muscat|sohar|salalah|difc|adgm|gcc|middle east|mena)\b",
    re.I,
)

FUNCTION = re.compile(
    r"strateg|transform|corporate develop|business develop|growth|planning|pmo|programme|program\b|portfolio|"
    r"product|islamic|shari|sukuk|takaful|partnership|alliance|investment|invest\b|m&a|mergers|capital market|dcm|"
    r"fundrais|investor relations|chief of staff|ceo office|office of the ceo|excellence|performance|innovation|"
    r"venture|enablement|commercial|general manager|business head|head of business|cfo|chief financial|finance director|"
    r"director of finance|head of finance|fp&a|governance|expansion|market intelligence|competitive intelligence|"
    r"value creation|value realisation|value realization|delivery|execution|strategic|business planning|"
    r"lending|mortgage|home finance|wealth|retail banking|digital|change|operating model|cost optimi|"
    r"automation|process excellence|advisory|consulting|thought leadership|capability|learning",
    re.I,
)

SENIOR = re.compile(
    r"\b(head|director|chief|cxo|c-level|vp|vice president|svp|evp|avp|lead|leader|senior manager|sr\.? manager|"
    r"general manager|gm|principal|partner|managing director|executive director|expert|senior advisor|advisor|"
    r"senior expert|country manager|business head)\b",
    re.I,
)

JUNIOR = re.compile(
    r"\b(analyst|officer|assistant|intern|internship|graduate|trainee|coordinator|clerk|teller|cashier|"
    r"junior|entry|apprentice|co-?op|representative|executive assistant|secretary|receptionist|driver|technician)\b",
    re.I,
)
JUNIOR_OK = re.compile(r"associate (director|partner|vice president)|senior associate director", re.I)

# Specialist backgrounds Zaid does not have
SPECIALIST = re.compile(
    r"\b(engineer|engineering|developer|software|devops|architect|nurse|physician|doctor|clinical|medical|pharmac|"
    r"legal counsel|lawyer|attorney|actuar|underwrit|it audit|cyber|security operations|network|sre|data scientist|"
    r"machine learning|chef|f&b|housekeeping|hse|qhse|construction manager|site manager|quantity surveyor|mep)\b",
    re.I,
)

NATIONALS = re.compile(
    r"(nationals? only|only (for )?(saudi|emirati|uae|qatari|omani|kuwaiti|bahraini) nationals?|"
    r"(saudi|uae|emirati|qatari|omani|kuwaiti|bahraini) nationals?\b(?! (and|or) expat)|for saudis only|"
    r"saudi[sz]ation|emirati[sz]ation|qatari[sz]ation|omani[sz]ation|kuwaiti[sz]ation|bahraini[sz]ation|"
    r"locals? preferred|national development program|family book|emirati candidates|"
    r"must be (a )?(saudi|emirati|uae|qatari|omani|kuwaiti|bahraini) national|"
    r"\((saudi|uae|qatari|omani|kuwaiti|bahraini|emirati)s?( nationals?)?( only)?\))",
    re.I,
)

ARABIC_MANDATORY = re.compile(
    r"(arabic (is )?(mandatory|required|a must|essential)|(fluent|fluency|proficien\w*|native)( in)? (english and )?arabic"
    r"(?![^.]{0,40}(preferred|advantage|plus|desirable|nice))|must (speak|be fluent in|read and write) arabic|"
    r"arabic speaker (only|required)|bilingual \(arabic|arabic (and|&) english (are )?(mandatory|required|essential))",
    re.I,
)


def title_score(title: str) -> int:
    """0 = drop. Higher = more relevant. Cheap pre-filter before Claude reviews."""
    t = title or ""
    if SPECIALIST.search(t):
        return 0
    if JUNIOR.search(t) and not JUNIOR_OK.search(t):
        return 0
    f, s = bool(FUNCTION.search(t)), bool(SENIOR.search(t))
    if f and s:
        score = 3
    elif s and re.search(r"\b(chief|head|director|general manager)\b", t, re.I):
        score = 2  # senior general titles (e.g. "Head of Retail", "Director")
    elif f and re.search(r"\bmanager\b", t, re.I):
        score = 1  # Manager-titled, may be senior in substance
    else:
        return 0
    if re.search(r"islamic|shari|sukuk|takaful", t, re.I):
        score += 2
    if re.search(r"strateg|corporate develop|growth|transform|pmo|chief of staff", t, re.I):
        score += 1
    return score


def text_flags(text: str) -> dict:
    text = text or ""
    n = NATIONALS.search(text)
    a = ARABIC_MANDATORY.search(text)
    return {
        "nationals_only": bool(n),
        "nationals_match": n.group(0) if n else None,
        "arabic_mandatory": bool(a),
        "arabic_match": a.group(0) if a else None,
    }


def in_gcc(location: str, employer_country: str | None = None, global_employer: bool = False) -> bool:
    if location and GCC.search(location):
        return True
    if not location and not global_employer:
        return True  # local GCC employer with no location text
    return False
