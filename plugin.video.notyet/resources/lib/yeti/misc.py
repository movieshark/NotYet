from requests import Session

from . import static


class RecordingError(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(f"{message} (code: {code})")
        self.code = code


class RecordingDeletionError(RecordingError):
    """Exception raised when a recording deletion fails."""

    pass


class RecordingCreationError(RecordingError):
    """Exception raised when a recording creation fails."""

    pass


def delete_recording(_session: Session, ks_token: str, media_id: int, **kwargs) -> str:
    """
    Delete a recording permanently from the user's recordings.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param media_id: The ID of the recording to delete
    :param kwargs: Optional arguments
    :return: The result of the deletion request
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "language": "hun",
        "ks": ks_token,
        "id": media_id,
        "clientTag": client_tag,
        "apiVersion": api_version,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/recording/action/delete",
        params=static.get_common_params(client_tag),
        json=data,
    )
    if response.json().get("result", {}).get("error"):
        raise RecordingDeletionError(
            response.json()["result"]["error"]["message"],
            response.json()["result"]["error"]["code"],
        )
    return response.json()["result"]["status"]


def create_single_recording(
    _session: Session, ks_token: str, media_id: int, **kwargs
) -> dict:
    """
    Create a recording for a single media item.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param media_id: The ID of the media item to record
    :param kwargs: Optional arguments
    :return: The result of the recording request
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    data = {
        "language": "hun",
        "ks": ks_token,
        "recording": {
            "objectType": f"{static.get_ott_platform_name()}Recording",
            "assetId": media_id,
        },
        "clientTag": client_tag,
        "apiVersion": api_version,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/recording/action/add",
        params=static.get_common_params(client_tag),
        json=data,
    )
    if response.json().get("result", {}).get("error"):
        raise RecordingCreationError(
            response.json()["result"]["error"]["message"],
            response.json()["result"]["error"]["code"],
        )
    return response.json()["result"]
