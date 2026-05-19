from datetime import date
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import randbelow, token_hex, token_urlsafe

PIN_HASH_ITERATIONS = 120_000


def generate_verification_code() -> str:
    return f'{randbelow(1_000_000):06d}'


def hash_verification_code(code: str) -> str:
    return sha256(code.strip().encode('utf-8')).hexdigest()


def hash_pin(pin: str) -> str:
    salt = token_hex(16)
    digest = pbkdf2_hmac('sha256', pin.strip().encode('utf-8'), salt.encode('utf-8'), PIN_HASH_ITERATIONS).hex()
    return f'pbkdf2_sha256${PIN_HASH_ITERATIONS}${salt}${digest}'


def verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        digest = pbkdf2_hmac('sha256', pin.strip().encode('utf-8'), salt.encode('utf-8'), int(iterations)).hex()
        return compare_digest(digest, expected)
    except Exception:
        return False


def generate_session_token() -> str:
    return token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return sha256(token.strip().encode('utf-8')).hexdigest()


def calculate_age(date_of_birth: date) -> int:
    today = date.today()
    birthday_passed = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if birthday_passed else 1)
