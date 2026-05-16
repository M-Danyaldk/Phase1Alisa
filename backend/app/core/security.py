from datetime import date
from hashlib import sha256
from secrets import randbelow


def generate_verification_code() -> str:
    return f'{randbelow(1_000_000):06d}'


def hash_verification_code(code: str) -> str:
    return sha256(code.strip().encode('utf-8')).hexdigest()


def calculate_age(date_of_birth: date) -> int:
    today = date.today()
    birthday_passed = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if birthday_passed else 1)
