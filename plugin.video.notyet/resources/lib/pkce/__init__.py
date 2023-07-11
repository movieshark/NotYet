from base64 import urlsafe_b64encode
from hashlib import sha256
from secrets import token_urlsafe
from typing import Tuple


def generate_code_verifier(length: int = 128) -> str:
    """
    Generate a code verifier.
    :param length: The length of the code verifier.
    :return: The code verifier.
    """
    return token_urlsafe(96)[:length]


def get_code_challenge(code_verifier: str) -> str:
    """
    Get a code challenge from a code verifier.
    :param code_verifier: The code verifier.
    :return: The code challenge.
    """
    hashed = sha256(code_verifier.encode("ascii")).digest()
    encoded = urlsafe_b64encode(hashed)
    code_challenge = encoded.decode("ascii")[:-1]
    return code_challenge


def generate_pkce_pair(code_verifier_length: int = 128) -> Tuple[str, str]:
    """
    Generate a PKCE code verifier and code challenge.
    :param code_verifier_length: The length of the code verifier.
    :return: A tuple containing the code verifier and code challenge.
    """
    code_verifier = generate_code_verifier(code_verifier_length)
    code_challenge = get_code_challenge(code_verifier)
    return code_verifier, code_challenge
