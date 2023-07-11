from typing import Tuple

from requests import Session

from . import static


class DeviceDeletionError(Exception):
    """Raised when a device deletion fails"""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(f"{message} (code: {code})")
        self.code = code


def get_devices(_session: Session, ks_token: str, **kwargs) -> tuple:
    """
    Get the devices registered to the user

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Optional arguments
    :return: A tuple containing the devices and the total number of devices
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "ks": ks_token,
        "language": "hun",
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/householddevice/action/list",
        params=static.get_common_params(client_tag),
        json=data,
    )
    return response.json()["result"]["objects"], response.json()["result"]["totalCount"]


def get_device_brands(_session: Session, ks_token: str, **kwargs) -> list:
    """
    Fetches the known device brands from the Yeti API

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Optional arguments
    :return: A list of device brands
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "ks": ks_token,
        "language": "hun",
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/devicebrand/action/list",
        params=static.get_common_params(client_tag),
        json=data,
    )
    return response.json()["result"]["objects"]


def delete_device(_session: Session, ks_token: str, ud_id: str, **kwargs) -> list:
    """
    Delete a device permanently from the user's household

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param ud_id: The device's ud_id
    :param kwargs: Optional arguments
    :return: A single item list containing the deletion result
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "ks": ks_token,
        "language": "hun",
        "udid": ud_id,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/householddevice/action/delete",
        params=static.get_common_params(client_tag),
        json=data,
    )
    if not isinstance(response.json().get("result"), bool) and response.json().get(
        "result", {}
    ).get("error"):
        raise DeviceDeletionError(
            response.json()["result"]["error"]["message"],
            response.json()["result"]["error"]["code"],
        )
    return response.json()["result"]


def get_streaming_devices(
    _session: Session, ks_token: str, **kwargs
) -> Tuple[list, int]:
    """
    Get the currently streaming devices registered to the user

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Optional arguments
    :return: A tuple containing the streaming device list and the
    total number of devices
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "apiVersion": api_version,
        "clientTag": client_tag,
        "ks": ks_token,
        "language": "hun",
        "filter": {
            "objectType": f"{static.get_ott_platform_name()}StreamingDeviceFilter"
        },
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/streamingdevice/action/list",
        params=static.get_common_params(client_tag),
        json=data,
    )
    return response.json()["result"]["objects"], response.json()["result"]["totalCount"]


def get_brands(_session: Session, ks_token: str, **kwargs) -> dict:
    """
    Calls the get_device_brands function and returns a dict
     where the key is the device id and the value is the device name

    :param _session: requests.Session object
    :param ks_token: KS Token
    :param kwargs: Optional arguments
    :return: dict
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    brands = get_device_brands(
        _session, ks_token, api_version=api_version, client_tag=client_tag
    )
    return {brand["id"]: brand["name"] for brand in brands}
