from base64 import b64decode
from functools import wraps

from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import unpad

_key = bytes.fromhex("6e6f7479657474767061737377726401")
_iv = bytes.fromhex("d70eac75d7d907ef0d2ba8f5bd4c5424")
app_version = "1.23.0"
app_version_with_build = "1.23.0-PC"
platform = "other"
device_brand = "22"
device_family = "5"
firmware = "n/a"
partner_id = "3204"
tv_pil_version = "1.14.0"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
special_ua_value = "JSClient/2.24.2"
realm = "sc-acc-prod"
api_version = "5.4.0"
ott_username = "11111"
ott_password = "11111"
channel_type = "613"
drm_api_version = "7.8.1"
drm_client_tag = "html5:v7.56"
movies_id = 357915


def get_common_params(client_tag: str = None) -> dict:
    """
    Returns a dict with the common parameters used in the API calls

    :return: dict
    """
    return {
        "format": 1,
        "clientTag": client_tag or app_version_with_build,
    }


cache = {}


def cache_result(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Generate a cache key based on function name and arguments
        cache_key = (func.__name__, args, frozenset(kwargs.items()))

        # Check if the result is already in the cache
        if cache_key in cache:
            return cache[cache_key]

        # If not in cache, compute the result and store it
        result = func(*args, **kwargs)
        cache[cache_key] = result
        return result

    return wrapper


def _decrypt_string(input: str):
    """
    Decrypts a string using AES-128-CBC with PKCS7 padding

    :param input: Encrypted string
    :return: Decrypted string
    """
    cipher = AES.new(_key, AES.MODE_CBC, _iv)
    return unpad(cipher.decrypt(b64decode(input)), 16, style="pkcs7").decode("utf-8")


@cache_result
def oauth_base() -> str:
    c = "OS1xuzVgzAzQHb0KEDeNAVVbEc5urpAxuMnw30sJXQPJTZcz9Sfvc0byVS0UWeDu7HRDmBsdYu/BWC88pbMbewTZmsCIf0r7lJ91CiwcpVY="
    return _decrypt_string(c)


@cache_result
def get_app_name() -> str:
    c = "cwkjb/M/Elz+U5QsYzF3r+8bBeNds+MTTfrhcmT2AXU="
    return _decrypt_string(c)


@cache_result
def get_special_ua_header() -> str:
    c = "0seEq7ZG4lhyG6O/BsGuk4UutyJxWjag0wCLytE+2c8="
    return _decrypt_string(c)


@cache_result
def get_base_url() -> str:
    c = "ddTYdm/A1BVLoOfZFa+B2l9y7j8Z+Z8GkMn1zVI/CAg="
    return _decrypt_string(c)


@cache_result
def get_oauth_ep() -> str:
    c = "uG8C4/WmxXGhwC46TUC8x0Igfo+4aKKcWfPStlpmBHrD/GkS/NZqxtWeQkHO+KfIwtrqMD7hfzlltMEGvnadTinTtXHGIGnqOHimcv4M/40="
    return _decrypt_string(c)


@cache_result
def get_access_token_ep() -> str:
    c = "uG8C4/WmxXGhwC46TUC8x5xX5gVLRHfhvRhZKLgqEBeV2Q6WfdsM6c0i5+6qsGcmDYgwq5S9vmRzDpSHfxSC4w=="
    return _decrypt_string(c)


@cache_result
def get_authorize_ep() -> str:
    c = "uG8C4/WmxXGhwC46TUC8x5xX5gVLRHfhvRhZKLgqEBeV2Q6WfdsM6c0i5+6qsGcmdhs5AnO3PAFRxw1/tnvscA=="
    return _decrypt_string(c)


@cache_result
def get_ott_base() -> str:
    c = "kCdvQby5nD+JHn0w+tlZGD8MwhjEiE8361nLs2zwHmNT5Y+fCWwEg06Z9y1B5Ai2"
    return _decrypt_string(c)


@cache_result
def get_ott_platform_name() -> str:
    c = "iRgwCNz7uGqqNiEqRNmEUA=="
    return _decrypt_string(c)


@cache_result
def get_drm_referrer() -> str:
    c = "qUJpBVDUHAzwykO3fCQgNxA/F4yJkJ8TFTpR8boCC/eWOEeKT6JmkSjEWO1Tf0gptPVpWuEBGXWSc4NI7BIt6w=="
    return _decrypt_string(c)


@cache_result
def get_oauth_domain() -> str:
    c = "RpocH1DQwVFTISljFoK+pQ=="
    return _decrypt_string(c)


if __name__ == "__main__":
    print("ouath_base:\t", oauth_base())
    print("app_name:\t", get_app_name())
    print("special_ua:\t", get_special_ua_header())
    print("base_url:\t", get_base_url())
    print("oauth_ep:\t", get_oauth_ep())
    print("access_token_ep:", get_access_token_ep())
    print("authorize_ep:\t", get_authorize_ep())
    print("ott_base:\t", get_ott_base())
    print("ott_platform:\t", get_ott_platform_name())
    print("drm_referrer:\t", get_drm_referrer())
    print("oauth_domain:\t", get_oauth_domain())
