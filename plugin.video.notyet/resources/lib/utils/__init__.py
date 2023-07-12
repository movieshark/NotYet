from datetime import datetime
from hashlib import sha256
from secrets import token_hex


def unix_to_date(unix_time: int) -> str:
    """
    Convert a UNIX timestamp to a date string. This method is
     used to tranlate times returned by the Yeti API to
     human-readable strings.

    :param unix_time: The UNIX timestamp.
    :return: The date string.
    """
    return datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")


def gen_desktop_udid() -> str:
    """
    Generate a desktop ud_id. This method is used to generate
     a unique identifier for the desktop device.
    Originally it uses Math.random(), takes the number after the decimal point,
    and hashes the whole thing. We use secrets.token_hex() instead.

    :return: The desktop ud_id.
    """
    key = token_hex(16)
    random_key = "WEB"  # seems to be hardcoded
    hash_value = sha256(f"{key}_{random_key}".encode()).hexdigest()
    udid = hash_value[:16].upper()
    return udid
