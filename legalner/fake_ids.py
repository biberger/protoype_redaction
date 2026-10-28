"""Random identifiers with valid check digits, for synthetic documents.

    python -m legalner.fake_ids iban AT 3      # three Austrian IBANs
    python -m legalner.fake_ids svnr 2         # Austrian social security numbers
    python -m legalner.fake_ids all            # one of everything
"""
import random
import re
import sys

IBAN_BBAN_LEN = {"AT": 16, "DE": 18, "CH": 17, "LI": 17, "FR": 23, "BE": 12, "LU": 16}


def iban(country="AT", rng=random):
    bban = "".join(rng.choice("0123456789") for _ in range(IBAN_BBAN_LEN[country]))
    numeric = "".join(str(int(c, 36)) for c in bban + country + "00")
    check = 98 - int(numeric) % 97
    raw = f"{country}{check:02d}{bban}"
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def iban_is_valid(value):
    s = value.replace(" ", "")
    numeric = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(numeric) % 97 == 1


SVNR_WEIGHTS = (3, 7, 9, 0, 5, 8, 4, 2, 1, 6)


def svnr(rng=random):
    """Austrian SV-Nummer: 3-digit serial, check digit, birth date DDMMYY."""
    while True:
        serial = f"{rng.randint(100, 999)}"
        dob = f"{rng.randint(1, 28):02d}{rng.randint(1, 12):02d}{rng.randint(0, 99):02d}"
        digits = [int(c) for c in serial + "0" + dob]
        check = sum(w * d for w, d in zip(SVNR_WEIGHTS, digits)) % 11
        if check < 10:
            return f"{serial}{check} {dob}"


def svnr_is_valid(value):
    s = value.replace(" ", "")
    digits = [int(c) for c in s]
    return len(s) == 10 and sum(w * d for w, d in zip(SVNR_WEIGHTS, digits)) % 11 == digits[3]


FN_LETTERS = "abdfghikmpstvwxyz"
FN_WEIGHTS = (6, 4, 14, 15, 10, 1)


def fn(rng=random):
    """Austrian Firmenbuchnummer with check letter, e.g. 'FN 123456a'."""
    number = rng.randint(1000, 650000)
    digits = [int(c) for c in f"{number:06d}"]
    letter = FN_LETTERS[sum(w * d for w, d in zip(FN_WEIGHTS, digits)) % 17]
    return f"FN {number}{letter}"


def fn_is_valid(value):
    m = re.fullmatch(r"(?:FN\s*)?(\d{1,6})\s*([a-z])", value.strip())
    if not m:
        return False
    digits = [int(c) for c in f"{int(m.group(1)):06d}"]
    return FN_LETTERS[sum(w * d for w, d in zip(FN_WEIGHTS, digits)) % 17] == m.group(2)


def nir(rng=random):
    """French social security number (NIR) with its 2-digit key."""
    body = (f"{rng.choice('12')}{rng.randint(0, 99):02d}{rng.randint(1, 12):02d}"
            f"{rng.randint(1, 95):02d}{rng.randint(1, 990):03d}{rng.randint(1, 999):03d}")
    key = 97 - int(body) % 97
    return f"{body[0]} {body[1:3]} {body[3:5]} {body[5:7]} {body[7:10]} {body[10:13]} {key:02d}"


def nir_is_valid(value):
    s = re.sub(r"\s", "", value).upper().replace("2A", "19").replace("2B", "18")
    return len(s) == 15 and s.isdigit() and 97 - int(s[:13]) % 97 == int(s[13:])


def ahv(rng=random):
    """Swiss AHV number 756.XXXX.XXXX.XC (EAN-13 check digit)."""
    digits = [7, 5, 6] + [rng.randint(0, 9) for _ in range(9)]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    s = "".join(map(str, digits + [(10 - total % 10) % 10]))
    return f"{s[:3]}.{s[3:7]}.{s[7:11]}.{s[11:]}"


def ahv_is_valid(value):
    s = re.sub(r"\D", "", value)
    if len(s) != 13 or not s.startswith("756"):
        return False
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(s[:12]))
    return (10 - total % 10) % 10 == int(s[12])


def uid_at(rng=random):
    """Austrian UID (ATU + 8 digits, check digit per BMF algorithm)."""
    d = [rng.randint(0, 9) for _ in range(7)]
    s = 0
    for i, x in enumerate(d):
        if i % 2:
            x = x * 2
            x = x // 10 + x % 10
        s += x
    check = (96 - s) % 10
    return "ATU" + "".join(map(str, d)) + str(check)


def uid_at_is_valid(value):
    s = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"ATU\d{8}", s):
        return False
    total = 0
    for i, c in enumerate(s[3:10]):
        x = int(c) * (2 if i % 2 else 1)
        total += x // 10 + x % 10
    return (96 - total) % 10 == int(s[10])


def _luhn_ok(digits):
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def _luhn_complete(body):
    return next(body + c for c in "0123456789" if _luhn_ok(body + c))


def siren(rng=random):
    """French SIREN: 8 random digits + Luhn check digit, written '123 456 789'."""
    s = _luhn_complete(f"{rng.randint(1, 99999999):08d}")
    return f"{s[:3]} {s[3:6]} {s[6:]}"


def siret(rng=random, siren_value=None):
    """French SIRET: SIREN + 4-digit NIC, Luhn over all 14 digits."""
    base = (siren_value or siren(rng)).replace(" ", "")
    s = _luhn_complete(base + f"{rng.randint(1, 999):04d}")
    return f"{s[:3]} {s[3:6]} {s[6:9]} {s[9:]}"


def siren_is_valid(value):
    s = re.sub(r"\s", "", value)
    return len(s) in (9, 14) and s.isdigit() and _luhn_ok(s)


def tva_fr(rng=random, siren_value=None):
    """French VAT number FR + 2-digit key + SIREN."""
    s = (siren_value or siren(rng)).replace(" ", "")
    return f"FR{(12 + 3 * (int(s) % 97)) % 97:02d}{s}"


def be_enterprise(rng=random):
    """Belgian enterprise number (KBO/BCE), '0123.456.749': 97 - first 8 digits mod 97."""
    body = rng.randint(2000000, 19999999)  # leading digit 0 or 1
    s = f"{body:08d}{97 - body % 97:02d}"
    return f"{s[:4]}.{s[4:7]}.{s[7:]}"


def be_enterprise_is_valid(value):
    s = re.sub(r"\D", "", value)
    return len(s) == 10 and s[0] in "01" and 97 - int(s[:8]) % 97 == int(s[8:])


CHE_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)


def che_uid(rng=random):
    """Swiss enterprise identifier CHE-123.456.789 (mod-11 check digit)."""
    while True:
        d = [rng.randint(0, 9) for _ in range(8)]
        check = 11 - sum(w * x for w, x in zip(CHE_WEIGHTS, d)) % 11
        if check == 11:
            check = 0
        if check < 10:
            s = "".join(map(str, d + [check]))
            return f"CHE-{s[:3]}.{s[3:6]}.{s[6:]}"


def che_uid_is_valid(value):
    s = re.sub(r"\D", "", value)
    if len(s) != 9:
        return False
    check = 11 - sum(w * int(x) for w, x in zip(CHE_WEIGHTS, s)) % 11
    return (0 if check == 11 else check) == int(s[8])


def ust_idnr_de(rng=random):
    """German USt-IdNr. DE + 9 digits, check digit per ISO 7064 MOD 11,10."""
    d = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(7)]
    return "DE" + "".join(map(str, d)) + str(_iso7064_11_10(d))


def _iso7064_11_10(digits):
    p = 10
    for x in digits:
        s = (x + p) % 10 or 10
        p = 2 * s % 11
    return (11 - p) % 10


def ust_idnr_de_is_valid(value):
    s = re.sub(r"\D", "", value)
    return len(s) == 9 and _iso7064_11_10([int(c) for c in s[:8]]) == int(s[8])


# DE Steuernummer in the notation of the Länder (Finanzamt prefix, district,
# serial). Check digits differ by Land and are not modelled: the numbers are
# format-correct only.
STNR_FORMATS = {
    "BW": "{f2}{f1}/{b3}/{u5}", "BY": "{f3}/{b3}/{u5}", "BE": "{f2}/{b3}/{u5}",
    "HB": "{f2} {b3} {u5}", "HH": "{f2}/{b3}/{u5}", "HE": "0{f2} {b3} {u5}",
    "NI": "{f2}/{b3}/{u5}", "NW": "{f3}/{b4}/{u4}", "SH": "{f2}/{b3}/{u5}",
    "SN": "2{f2}/{b3}/{u5}", "RP": "{f2}/{b3}/{u4}/{u1}",
}


def steuernummer_de(rng=random, land=None):
    land = land or rng.choice(sorted(STNR_FORMATS))
    r = lambda n: "".join(rng.choice("0123456789") for _ in range(n))
    return STNR_FORMATS[land].format(f1=r(1), f2=r(2), f3=r(3), b3=r(3), b4=r(4),
                                     u1=r(1), u4=r(4), u5=r(5))


RVNR_WEIGHTS = (2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1)
RVNR_AREAS = ("02", "03", "04", "08", "09", "10", "11", "12", "13", "14", "15", "16",
              "17", "18", "19", "20", "21", "23", "24", "25", "26", "28", "29", "38",
              "39", "40", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51",
              "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62", "63",
              "64", "65", "66", "67", "68", "69", "70", "71", "72", "73", "74", "75",
              "76", "77", "78", "79", "80", "81", "82", "89")


def _rvnr_check(first11):
    """first11 = area(2) + DDMMYY(6) + letter + serial(2)."""
    digits = first11[:8] + f"{ord(first11[8].upper()) - 64:02d}" + first11[9:]
    total = sum(sum(divmod(w * int(c), 10)) for w, c in zip(RVNR_WEIGHTS, digits))
    return total % 10


def rvnr(rng=random, female=None):
    """German Rentenversicherungsnummer '15 070649 C 103': area, DOB, initial of
    birth name, serial (00-49 male, 50-99 female), check digit."""
    female = rng.random() < 0.5 if female is None else female
    body = (rng.choice(RVNR_AREAS)
            + f"{rng.randint(1, 28):02d}{rng.randint(1, 12):02d}{rng.randint(0, 99):02d}"
            + rng.choice("ABDEFGHKLMNPRSTWZ")
            + f"{rng.randint(50, 99) if female else rng.randint(0, 49):02d}")
    return f"{body[:2]} {body[2:8]} {body[8]} {body[9:]}{_rvnr_check(body)}"


def rvnr_is_valid(value):
    s = re.sub(r"\s", "", value)
    return bool(re.fullmatch(r"\d{8}[A-Za-z]\d{3}", s)) and _rvnr_check(s[:11]) == int(s[11])


DE_REGISTER_COURTS = ("Amtsgericht München", "Amtsgericht Charlottenburg", "Amtsgericht Hamburg",
                      "Amtsgericht Köln", "Amtsgericht Frankfurt am Main", "Amtsgericht Düsseldorf",
                      "Amtsgericht Stuttgart", "Amtsgericht Leipzig", "Amtsgericht Hannover",
                      "Amtsgericht Nürnberg", "Amtsgericht Mannheim", "Amtsgericht Bremen")


def hrb(rng=random, kind=None):
    """German commercial register number, e.g. 'HRB 209877' or 'HRA 88421' (no check digit).
    Berlin numbers carry a trailing 'B'. Pair with a court from DE_REGISTER_COURTS."""
    kind = kind or rng.choices(("HRB", "HRA"), (5, 1))[0]
    n = rng.randint(100, 299999)
    return f"{kind} {n}" + (" B" if rng.random() < 0.1 else "")


GENERATORS = {"svnr": svnr, "fn": fn, "nir": nir, "ahv": ahv, "uid_at": uid_at,
              "steuernummer_de": steuernummer_de, "ust_idnr_de": ust_idnr_de, "rvnr": rvnr,
              "hrb": hrb, "che_uid": che_uid, "siren": siren, "siret": siret, "tva_fr": tva_fr,
              "be_enterprise": be_enterprise}


def main(argv):
    if not argv:
        sys.exit(__doc__)
    kind, rest = argv[0], argv[1:]
    if kind == "all":
        for c in IBAN_BBAN_LEN:
            print(f"iban {c}: {iban(c)}")
        for name, gen in GENERATORS.items():
            print(f"{name}: {gen()}")
        return
    if kind == "iban":
        country = rest[0] if rest else "AT"
        n = int(rest[1]) if len(rest) > 1 else 1
        print(*(iban(country) for _ in range(n)), sep="\n")
        return
    n = int(rest[0]) if rest else 1
    print(*(GENERATORS[kind]() for _ in range(n)), sep="\n")


if __name__ == "__main__":
    main(sys.argv[1:])
