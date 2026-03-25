import hashlib
from datetime import datetime, timedelta
import re

SECRET_WORD = "NFE_READER_SECRET_2026"

def generate_key(cnpj: str, hwid: str, days: int) -> str:
    cnpj_clean = re.sub(r'[^0-9]', '', cnpj)

    exp_date = datetime.now() + timedelta(days=days)
    exp_date_str = exp_date.strftime("%Y-%m-%d")

    payload = f"{cnpj_clean}|{exp_date_str}|{hwid}|{SECRET_WORD}"
    hash_val = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8].upper()

    key = f"NFE-{cnpj_clean}-{exp_date_str}-{hash_val}"
    return key