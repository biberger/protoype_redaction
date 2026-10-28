"""Random identifiers with valid check digits, for synthetic documents.

    python -m legalner.fake_ids iban AT 3      # three Austrian IBANs
    python -m legalner.fake_ids svnr 2         # Austrian social security numbers
    python -m legalner.fake_ids all            # one of everything
"""
import random
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


def nir(rng=random):
    """French social security number (NIR) with its 2-digit key."""
    body = (f"{rng.choice('12')}{rng.randint(0, 99):02d}{rng.randint(1, 12):02d}"
            f"{rng.randint(1, 95):02d}{rng.randint(1, 990):03d}{rng.randint(1, 999):03d}")
    key = 97 - int(body) % 97
    return f"{body[0]} {body[1:3]} {body[3:5]} {body[5:7]} {body[7:10]} {body[10:13]} {key:02d}"


def ahv(rng=random):
    """Swiss AHV number 756.XXXX.XXXX.XC (EAN-13 check digit)."""
    digits = [7, 5, 6] + [rng.randint(0, 9) for _ in range(9)]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    s = "".join(map(str, digits + [(10 - total % 10) % 10]))
    return f"{s[:3]}.{s[3:7]}.{s[7:11]}.{s[11:]}"


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


GENERATORS = {"svnr": svnr, "fn": fn, "nir": nir, "ahv": ahv, "uid_at": uid_at}


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
