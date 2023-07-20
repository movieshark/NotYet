from requests import Session

from . import static


def get_playback_obj(_session: Session, ks_token: str, media_id: int, **kwargs) -> dict:
    """
    Get the playback object for a media item. This is used to get the playback URL and
     optionally the DRM details. Right now MPEG-DASH is hardcoded.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param media_id: The ID of the media item
    :param kwargs: Optional arguments
    :return: The playback object
    """
    drm_api_version = kwargs.get("drm_api_version", static.drm_api_version)
    partner_id = kwargs.get("partner_id", static.partner_id)
    asset_reference_type = kwargs.get("asset_reference_type", "media")
    asset_type = kwargs.get("asset_type", "media")
    data = {
        "1": {
            "service": "asset",
            "action": "get",
            "id": media_id,
            "assetReferenceType": asset_reference_type,
            "ks": ks_token,
        },
        "2": {
            "service": "asset",
            "action": "getPlaybackContext",
            "assetId": media_id,
            "assetType": asset_type,
            "contextDataParams": {
                "objectType": f"{static.get_ott_platform_name()}PlaybackContextOptions",
                "context": "CATCHUP" if asset_type == "epg" else "PLAYBACK",
                "streamerType": "mpegdash",
                "urlType": "DIRECT",
            },
            "ks": ks_token,
        },
        "apiVersion": drm_api_version,
        "ks": ks_token,
        "partnerId": partner_id,
    }
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/multirequest",
        json=data,
    )
    return response.json()["result"]
