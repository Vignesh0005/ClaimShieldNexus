"""Procedure and diagnosis code helpers. The code sets below are small illustrative samples for
the demo; a production deployment loads the licensed CPT set and the quarterly CMS NCCI edit files."""
import re

CPT_RE = re.compile(r"^(\d{5}|\d{4}[A-Z])$")
HCPCS_RE = re.compile(r"^[A-V]\d{4}$")
ICD10_RE = re.compile(r"^[A-TV-Z]\d[0-9A-Z](\.[0-9A-Z]{1,4})?$")

EM_ESTABLISHED = ["99211", "99212", "99213", "99214", "99215"]
EM_NEW = ["99202", "99203", "99204", "99205"]
EM_CODES = set(EM_ESTABLISHED + EM_NEW)
EM_HIGH_LEVEL = {"99215", "99205"}

# Typical minutes per unit, used to add up a provider's billed time in one day.
TYPICAL_MINUTES = {
    "99211": 5, "99212": 15, "99213": 25, "99214": 35, "99215": 50,
    "99202": 20, "99203": 35, "99204": 50, "99205": 70,
    "90832": 30, "90834": 45, "90837": 60,
    "97110": 15, "97112": 15, "97140": 15, "97530": 15,
}

# (comprehensive code, component code): billing both on one claim needs a distinct-service modifier.
NCCI_PAIRS = {
    ("80053", "80048"), ("80053", "82947"), ("80053", "84450"), ("80053", "82565"),
    ("85025", "85027"), ("85025", "85004"), ("93000", "93005"), ("93000", "93010"),
    ("99215", "99213"), ("99214", "99212"), ("43239", "43235"), ("29881", "29877"),
}
NCCI_BYPASS_MODIFIERS = {"59", "XE", "XS", "XP", "XU", "25"}

# Panels and the component tests they bundle.
PANELS = {
    "80053": {"82040", "82247", "82310", "82374", "82435", "82565", "82947", "84075", "84132", "84155", "84295", "84450", "84460", "84520"},
    "80048": {"82310", "82374", "82435", "82565", "82947", "84132", "84295", "84520"},
    "80061": {"82465", "83718", "84478"},
}

DME_PREFIXES = ("E", "K", "L")

# Most units of one code that one claim would normally carry for a single day of service.
MAX_UNITS_PER_DAY = {
    "99211": 1, "99212": 1, "99213": 1, "99214": 1, "99215": 1, "99202": 1, "99203": 1, "99204": 1, "99205": 1,
    "90832": 1, "90834": 1, "90837": 1,
    "97110": 6, "97112": 4, "97140": 4, "97530": 6,
    "80053": 1, "80048": 1, "80061": 1, "85025": 1, "36415": 2, "93000": 2,
    "E0601": 1, "29881": 1, "66984": 1, "45378": 1, "43239": 1,
}

# Typical billed amount for one unit of a code, used when a tenant has too little history of its own.
TYPICAL_AMOUNTS = {
    "99211": 45, "99212": 75, "99213": 120, "99214": 180, "99215": 260, "99202": 110, "99203": 170, "99204": 250, "99205": 330,
    "90832": 90, "90834": 125, "90837": 160,
    "97110": 40, "97112": 42, "97140": 38, "97530": 45,
    "80053": 45, "80061": 40, "85025": 30, "36415": 12, "93000": 55,
    "E0601": 900, "29881": 4200, "66984": 3200, "45378": 1100, "43239": 1300,
}

# Diagnosis prefixes treated as long-term conditions for waiting-period and member-harm checks.
CHRONIC_DX_PREFIXES = ("E10", "E11", "I10", "I11", "I20", "I25", "I50", "J44", "J45", "N18", "M05", "M06", "C")
COSMETIC_DX = {"Z41.1", "L90.5", "L91.0"}
COSMETIC_CPT_RANGES = [(15775, 15839), (15876, 15879), (19316, 19325), (30400, 30450)]
DENTAL_DX_PREFIXES = ("K00", "K01", "K02", "K03", "K04", "K05", "K06", "K08")
INFERTILITY_DX_PREFIXES = ("N97", "N46", "Z31")
SPECIFIC_WAITING_DX_PREFIXES = ("H25", "H26", "K40", "K41", "K42", "K43", "K80", "M16", "M17", "N40", "N20")
MATERNITY_DX_PREFIXES = ("O", "Z33", "Z34", "Z3A")
DAYCARE_CPT = {"66984", "45378", "43239", "90935", "96413", "29881", "52000"}

# Diagnosis groups by ICD-10 prefix, and the groups each procedure is normally billed with.
DX_GROUPS = {
    "eye": ("H0", "H1", "H2", "H3", "H4", "H5"),
    "ear": ("H6", "H7", "H8", "H9"),
    "musculoskeletal": ("M",),
    "injury": ("S", "T"),
    "circulatory": ("I",),
    "respiratory": ("J",),
    "digestive": ("K",),
    "genitourinary": ("N",),
    "pregnancy": ("O", "Z33", "Z34", "Z3A"),
    "mental_health": ("F",),
    "skin": ("L",),
    "endocrine": ("E",),
    "neoplasm": ("C", "D0", "D1", "D2", "D3", "D4"),
    "symptoms_and_screening": ("R", "Z12"),
}
PROCEDURE_DX_GROUPS = {
    "29881": ("Knee arthroscopy", ("musculoskeletal", "injury")),
    "29877": ("Knee arthroscopy", ("musculoskeletal", "injury")),
    "66984": ("Cataract surgery", ("eye",)),
    "45378": ("Colonoscopy", ("digestive", "neoplasm", "symptoms_and_screening")),
    "43239": ("Upper GI endoscopy", ("digestive", "neoplasm", "symptoms_and_screening")),
    "43235": ("Upper GI endoscopy", ("digestive", "neoplasm", "symptoms_and_screening")),
    "52000": ("Cystoscopy", ("genitourinary", "neoplasm", "symptoms_and_screening")),
    "90935": ("Haemodialysis", ("genitourinary",)),
    "96413": ("Chemotherapy infusion", ("neoplasm",)),
    "59400": ("Obstetric care", ("pregnancy",)),
    "59510": ("Obstetric care", ("pregnancy",)),
}

# Age and gender limits for services that only apply to some members. Ages are in whole years.
PROCEDURE_DEMOGRAPHICS = {
    "59400": {"service": "Obstetric care", "gender": "F", "min_age": 12, "max_age": 55},
    "59510": {"service": "Obstetric care", "gender": "F", "min_age": 12, "max_age": 55},
    "76805": {"service": "Obstetric ultrasound", "gender": "F", "min_age": 12, "max_age": 55},
    "58150": {"service": "Hysterectomy", "gender": "F"},
    "55700": {"service": "Prostate biopsy", "gender": "M"},
    "55866": {"service": "Prostatectomy", "gender": "M"},
    "84153": {"service": "Prostate-specific antigen test", "gender": "M"},
    "99460": {"service": "Newborn care", "max_age": 0},
    "99381": {"service": "Preventive visit, infant", "max_age": 0},
    "99382": {"service": "Preventive visit, age 1 to 4", "min_age": 1, "max_age": 4},
    "99383": {"service": "Preventive visit, age 5 to 11", "min_age": 5, "max_age": 11},
    "99384": {"service": "Preventive visit, age 12 to 17", "min_age": 12, "max_age": 17},
    "99385": {"service": "Preventive visit, age 18 to 39", "min_age": 18, "max_age": 39},
    "99386": {"service": "Preventive visit, age 40 to 64", "min_age": 40, "max_age": 64},
    "99387": {"service": "Preventive visit, age 65 and over", "min_age": 65},
}

# Kinds of service a member would not normally obtain from many different providers in one month.
SERVICE_GROUPS = {
    **{code: "office_visit" for code in EM_ESTABLISHED + EM_NEW},
    "90832": "psychotherapy", "90834": "psychotherapy", "90837": "psychotherapy",
    "97110": "physical_therapy", "97112": "physical_therapy", "97140": "physical_therapy", "97530": "physical_therapy",
    "20610": "pain_injection", "64483": "pain_injection", "62323": "pain_injection",
    "E0601": "sleep_equipment", "E0470": "sleep_equipment",
    "70450": "advanced_imaging", "72148": "advanced_imaging", "73721": "advanced_imaging",
}


def dx_groups(code: str | None) -> list[str]:
    return [group for group, prefixes in DX_GROUPS.items() if code and code.upper().startswith(prefixes)]


def is_valid_procedure_code(code: str | None) -> bool:
    return bool(code) and bool(CPT_RE.match(code) or HCPCS_RE.match(code))


def is_valid_icd10(code: str | None) -> bool:
    return bool(code) and bool(ICD10_RE.match(code.upper()))


def has_prefix(codes: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return [c for c in codes if c and c.upper().startswith(prefixes)]


def in_ranges(code: str | None, ranges: list[tuple[int, int]]) -> bool:
    if not code or not code.isdigit():
        return False
    return any(lo <= int(code) <= hi for lo, hi in ranges)


SAMPLE_DISCLAIMER = "Sample code pairs. Not for production use."

# Provenance of the code tables above, reported by GET /api/v1/coverage/compliance-report.
REFERENCE_DATA = [
    {"name": "NCCI procedure-to-procedure pairs", "entries": len(NCCI_PAIRS), "used_by": "ncci_edit rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": SAMPLE_DISCLAIMER, "production_source": "CMS NCCI quarterly edit files"},
    {"name": "Laboratory panel components", "entries": len(PANELS), "used_by": "unbundling rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample panels. Not for production use.", "production_source": "Licensed CPT code set"},
    {"name": "Typical minutes per procedure code", "entries": len(TYPICAL_MINUTES), "used_by": "impossible_timing rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample durations. Not for production use.", "production_source": "Licensed CPT code set and payer policy"},
    {"name": "Evaluation and management code levels", "entries": len(EM_CODES), "used_by": "upcoding rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample code list. Not for production use.", "production_source": "Licensed CPT code set"},
    {"name": "Diagnosis groupings for waiting periods and exclusions", "entries": len(CHRONIC_DX_PREFIXES) + len(SPECIFIC_WAITING_DX_PREFIXES) + len(COSMETIC_DX) + len(DENTAL_DX_PREFIXES) + len(INFERTILITY_DX_PREFIXES), "used_by": "coverage rules", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample diagnosis groupings. Not for production use.", "production_source": "Insurer policy wording"},
    {"name": "Maximum units per code per day", "entries": len(MAX_UNITS_PER_DAY), "used_by": "units_cap rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample unit limits. Not for production use.", "production_source": "CMS Medically Unlikely Edit files and payer policy"},
    {"name": "Typical billed amount per procedure code", "entries": len(TYPICAL_AMOUNTS), "used_by": "amount_outlier and split_billing rules", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample amounts. Not for production use.", "production_source": "Payer fee schedule or the tenant's own claim history"},
    {"name": "Procedure-to-diagnosis compatibility groups", "entries": len(PROCEDURE_DX_GROUPS), "used_by": "diagnosis_procedure_mismatch rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample code groupings. Not for production use.", "production_source": "CMS coverage determinations and payer medical policy"},
    {"name": "Age and gender limits per procedure code", "entries": len(PROCEDURE_DEMOGRAPHICS), "used_by": "demographic_mismatch rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample age and gender limits. Not for production use.", "production_source": "Licensed CPT code set and payer medical policy"},
    {"name": "Service groups for provider shopping", "entries": len(SERVICE_GROUPS), "used_by": "provider_shopping rule", "authoritative": False, "needs_compliance_review": True, "disclaimer": "Sample service groupings. Not for production use.", "production_source": "Payer service categories"},
]
