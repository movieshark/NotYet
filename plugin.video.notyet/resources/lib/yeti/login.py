from base64 import b64encode
from json import dumps
from typing import Tuple
from urllib.parse import parse_qs, urlencode

from requests import Session
from resources.lib.pkce import generate_pkce_pair

from . import static


class LoginFailed(Exception):
    """Base class for login errors"""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(f"{message} (code: {code})")
        self.code = code


class RefreshSessionFailed(LoginFailed):
    """Raised when the session refreshing fails"""

    pass


class AddHouseHoldDeviceError(Exception):
    """Raised when adding a household device fails"""

    pass


class DeviceNotRegistered(Exception):
    """Raised when the device is not yet registered"""

    pass


def get_oauth_params(_session: Session, device_id: str, **kwargs) -> Tuple[str, dict]:
    """
    Get OAuth params for Yeti OAuth login later.
    Throws AssertionErrors if OAuth details are missing from the response.

    :param _session: requests.Session object
    :param device_id: The device ID
    :param params: Additional params
    :return: A tuple containing the device ID and the OAuth params"""
    version = kwargs.get("app_version", static.app_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    partner_id = kwargs.get("partner_id", static.partner_id)
    user_agent = kwargs.get("user_agent", static.user_agent)
    platform = kwargs.get("platform", static.platform)
    device_family = kwargs.get("device_family", static.device_family)
    device_brand = kwargs.get("device_brand", static.device_brand)
    firmware = kwargs.get("firmware", static.firmware)
    tv_pil_version = kwargs.get("tv_pil_version", static.tv_pil_version)
    # construct the base64 part of the URL with some device info
    data = {
        "key": device_id,
        "name": "anonymous",
        "anonymous": True,
        "custom": {
            "applicationName": static.get_app_name(),
            "clientTag": client_tag,
            "clientVersion": version,
            "consumerEmail": "",
            "platform": platform,
            "deviceBrand": device_brand,
            "deviceFamily": device_family,
            "firmware": firmware,
            "partnerId": partner_id,
            "release": f"{static.get_app_name()}@{version}",
            "tvpilVersion": tv_pil_version,
            "osVersion": user_agent.split("/", 1)[1],
        },
    }
    data = b64encode(dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    response = _session.get(
        f"{static.oauth_base()}{data}",
        headers={
            static.get_special_ua_header(): static.special_ua_value,
        },
    )
    json_data = response.json()
    auth_params = json_data.get("AUTH_PARAMS", {}).get("value")
    assert auth_params, "AUTH_PARAMS not found in response"
    auth_base = auth_params.get("oauthBaseUrl")
    assert auth_base, "oauthBaseUrl not found in response"
    response_type = auth_params.get("oAuthResponseType")
    assert response_type, "oAuthResponseType not found in response"
    client_id = auth_params.get("oAuthClientId")
    assert client_id, "oAuthClientId not found in response"
    code_challenge_method = auth_params.get("oAuthCodeChallengeMethod")
    assert code_challenge_method, "oAuthCodeChallengeMethod not found in response"
    scope = auth_params.get("oAuthScope")
    assert scope, "oAuthScope not found in response"
    code_verifier, code_challenge = generate_pkce_pair(43)
    auth_params = {
        "response_type": response_type,
        "client_id": client_id,
        "redirect_uri": f"{static.get_base_url()}/auth/",
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
    }
    return code_verifier, auth_params


def login(
    _session: str, device_id: str, email: str, password: str, **kwargs
) -> Tuple[str, str, int]:
    """
    Login to Yeti's OAuth portal with the given credentials.
    Throws LoginFailed if the login fails.

    :param _session: requests.Session object
    :param device_id: The device ID
    :param email: The email address
    :param password: The password
    :param kwargs: Additional params
    :return: A tuple containing the access token, refresh token
     and the expiry time in seconds (ie. 3599)
    """
    realm = kwargs.get("realm", static.realm)
    code_verifier, auth_params = get_oauth_params(_session, device_id, **kwargs)
    headers = {
        "X-Username": "anonymous",  # TODO: don't hardcode these
        "X-Password": "anonymous",
        "X-Requested-With": "XMLHttpRequest",
        "X-Device-Id": device_id,
    }
    params = {
        "realm": "/" + realm,
        "goto": f"{static.get_authorize_ep()}?{urlencode(auth_params)}",
    }
    # first request to get the login object
    response = _session.post(
        f"{static.get_oauth_ep()}authenticate", params=params, headers=headers
    )
    json_data = response.json()
    # fills in the login object with the credentials and send it back
    json_data["callbacks"][0]["input"][0]["value"] = email
    json_data["callbacks"][1]["input"][0]["value"] = password
    response = _session.post(
        f"{static.get_oauth_ep()}authenticate",
        params=params,
        json=json_data,
        headers=headers,
    )
    if not response.ok:
        json_data = response.json()
        raise LoginFailed(json_data["message"], json_data["code"])
    # extracts tokenId from response
    json_data = response.json()
    token_id = json_data["tokenId"]
    # NOTE: cookie is required for future auth requests
    _session.cookies.set(
        "iPlanetDirectoryPro", token_id, domain=static.get_oauth_domain()
    )
    # requests grant code
    response = _session.get(
        static.get_authorize_ep(), params=auth_params, headers=headers
    )
    query = parse_qs(response.url.split("?", 1)[1])
    code = query["code"][0]
    data = {
        "grant_type": "authorization_code",
        "client_id": auth_params["client_id"],
        "code": code,
        "redirect_uri": auth_params["redirect_uri"],
        "code_verifier": code_verifier,
    }
    # requests OAuth access token
    response = _session.post(static.get_access_token_ep(), data=data, headers=headers)
    access_token = response.json()["access_token"]
    refresh_token = response.json()["refresh_token"]
    expires_in = response.json()["expires_in"]
    return access_token, refresh_token, expires_in


def anonymous_login(_session: Session, **kwargs) -> Tuple[str, str, str]:
    """
    Login to Yeti anonymously.
    This is required to later escalate to a full account.

    :param _session: requests.Session object
    :param kwargs: Additional params
    :return: A tuple containing the ks token, refresh token
     and the expiry time in UNIX time
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    partner_id = kwargs.get("partner_id", static.partner_id)
    params = static.get_common_params(client_tag)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "language": "*",
        "partnerId": partner_id,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/ottuser/action/anonymousLogin",
        params=params,
        json=data,
    )
    ks_token = response.json()["result"]["ks"]
    refresh_token = response.json()["result"]["refreshToken"]
    expiry = response.json()["result"]["expiry"]
    return ks_token, refresh_token, expiry


def login_ott(
    _session: Session, access_token: str, ks_token: str, ud_id: str, **kwargs
) -> Tuple[str, str, int]:
    """
    Fully logins to Yeti using an anonymous session
    and an OAuth access token.

    :param _session: requests.Session object
    :param access_token: The access token
    :param ks_token: The ks token
    :param ud_id: The device ID
    :param kwargs: Additional params
    :return: A tuple containing the access token, refresh token
     and the expiry time in UNIX time
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    partner_id = kwargs.get("partner_id", static.partner_id)
    ott_password = kwargs.get("ott_password", static.ott_password)
    ott_username = kwargs.get("ott_username", static.ott_username)
    params = static.get_common_params(client_tag)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "extraParams": {
            "accessToken": {
                "objectType": f"{static.get_ott_platform_name()}StringValue",
                "value": access_token,
            },
            "loginType": {
                "objectType": f"{static.get_ott_platform_name()}StringValue",
                "value": "accessToken",
            },
        },
        "ks": ks_token,
        "language": "hun",
        "partnerId": partner_id,
        "password": ott_password,
        "udid": ud_id,
        "username": ott_username,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/ottuser/action/login",
        params=params,
        json=data,
    )
    if response.json().get("result", {}).get("error"):
        raise LoginFailed(
            response.json()["result"]["error"]["message"],
            response.json()["result"]["error"]["code"],
        )
    ks_token = response.json()["result"]["loginSession"]["ks"]
    refresh_token = response.json()["result"]["loginSession"]["refreshToken"]
    expiry = response.json()["result"]["loginSession"]["expiry"]
    return ks_token, refresh_token, expiry


def get_household_device(_session: Session, ks_token: str, **kwargs) -> str:
    """
    Gets the device ID of the current device if it is already registered.
    If it is not, it will raise a DeviceNotRegistered exception.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Additional params
    :return: The device ID
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    params = static.get_common_params(client_tag)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "ks": ks_token,
        "language": "hun",
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/householddevice/action/get",
        params=params,
        json=data,
    )
    if (
        response.json().get("result", {}).get("error", {}).get("message")
        == "DeviceNotExists"
    ):
        raise DeviceNotRegistered()
    return response.json()["result"]["udid"]


def add_device_to_household(
    _session: Session, ks_token: str, ud_id: str, **kwargs
) -> str:
    """
    Adds current device to the current user's Yeti household.
    If the device is already registered or if the quota is exceeded,
     it will raise an AddHouseHoldDeviceError exception.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param ud_id: The device ID
    :param kwargs: Additional params
    :return: The device ID
    """
    name = kwargs.get("name", "")
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    device_brand = kwargs.get("device_brand", static.device_brand)
    params = static.get_common_params(client_tag)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "device": {
            "objectType": f"{static.get_ott_platform_name()}HouseholdDevice",
            "udid": ud_id,
            "name": name,
            "brandId": device_brand,
        },
        "ks": ks_token,
        "language": "hun",
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/householddevice/action/add",
        params=params,
        json=data,
    )
    if response.json().get("result", {}).get("state") == "activated":
        return response.json()["result"]["udid"]
    else:
        raise AddHouseHoldDeviceError(
            response.json()["result"]["error"]["message"],
        )


def get_or_add_device_to_household(
    _session: Session, ks_token: str, ud_id: str, **kwargs
) -> str:
    """
    Gets or adds current device to Yeti household. If the device is already
     registered, it will return the device ID. If it is not, it will add it
     to the household and return the device ID.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param ud_id: The device ID
    :param kwargs: Additional params
    :return: The device ID
    """
    try:
        return get_household_device(_session, ks_token, **kwargs)
    except DeviceNotRegistered:
        return add_device_to_household(_session, ks_token, ud_id, **kwargs)


def refresh_ks_token(
    _session: Session, ks_token: str, refresh_token: str, **kwargs
) -> Tuple[str, str, int]:
    """
    Refreshes the ks token.
    Might raise a RefreshTokenError exception.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param refresh_token: The refresh token
    :param kwargs: Additional params
    :return: The new ks token, refresh token and expiry
    """
    # NOTE: Couldn't find this in the official apps, inspiracy from
    # https://github.com/kaltura/playkit-android/blob/035df79917fdae4a9feb453335974a3ff2c0ca5b/playkit/src/main/java/com/kaltura/playkit/backend/phoenix/services/OttUserService.java#L56-L74
    # but mostly guesswork
    ud_id = kwargs.get("ud_id", None)
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    params = static.get_common_params(client_tag)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "refreshToken": refresh_token,
        "ks": ks_token,
        "language": "hun",
    }
    if ud_id:
        data["udid"] = ud_id
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/ottuser/action/refreshSession",
        params=params,
        json=data,
    )
    if response.json().get("result", {}).get("error"):
        raise RefreshSessionFailed(
            response.json()["result"]["error"]["message"],
            response.json()["result"]["error"]["code"],
        )
    ks_token = response.json()["result"]["ks"]
    refresh_token = response.json()["result"]["refreshToken"]
    expiry = response.json()["result"]["expiry"]
    return ks_token, refresh_token, expiry
