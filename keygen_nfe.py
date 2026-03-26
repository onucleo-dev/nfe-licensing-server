import hashlib
import os
from datetime import datetime, timedelta
import re

SECRET_WORD = os.getenv("SECRET_WORD", "NFE_READER_SECRET_2026")


def generate_key(cnpj: str, hwid: str, days: int) -> str:
    if not cnpj or not hwid:
        raise ValueError("cnpj and hwid are required")

    cnpj_clean = re.sub(r'[^0-9]', '', cnpj)
    if len(cnpj_clean) not in (11, 14):
        raise ValueError("cnpj must be a valid CPF/CNPJ format")

    if not isinstance(days, int) or days <= 0:
        raise ValueError("days must be a positive integer")

    exp_date = datetime.now() + timedelta(days=days)
    exp_date_str = exp_date.strftime("%Y-%m-%d")

    payload = f"{cnpj_clean}|{exp_date_str}|{hwid}|{SECRET_WORD}"
    hash_val = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()

    return f"NFE-{cnpj_clean}-{exp_date_str}-{hash_val}"
