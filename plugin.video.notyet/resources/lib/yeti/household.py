from requests import Session

from . import static


def get_household(_session: Session, ks_token: str, **kwargs) -> dict:
    """
    Fetches the user's household from the Yeti API

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Optional arguments
    :return: The user's household
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    params = static.get_common_params(client_tag)
    data = {
        "ks": ks_token,
        "clientTag": client_tag,
        "apiVersion": api_version,
        "language": "hun",
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/household/action/get",
        params=params,
        json=data,
    )
    return response.json()["result"]
