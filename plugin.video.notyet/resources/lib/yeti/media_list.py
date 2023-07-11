from typing import Tuple

from requests import Session

from . import static


def filter(
    _session: Session, filter_obj: dict, ks_token: str, page_idx: int = 1, **kwargs
) -> Tuple[list, int]:
    """
    Calls the list ep with a provided filter object.

    :param _session: requests.Session object
    :param filter_obj: The filter object
    :param ks_token: The ks token
    :param page_idx: The page index
    :param kwargs: Optional arguments (ie. response_profile: dict, page_size: int = 500)
    :return: A tuple containing the list of media items and the total number of items
    """
    api_version = kwargs.get("api_version", static.api_version)
    client_tag = kwargs.get("client_tag", static.app_version_with_build)
    page_size = kwargs.get("page_size", 500)
    params = static.get_common_params(client_tag)
    data = {
        "language": "hun",
        "ks": ks_token,
        "filter": filter_obj,
        "pager": {
            "objectType": f"{static.get_ott_platform_name()}FilterPager",
            "pageSize": page_size,
            "pageIndex": page_idx,
        },
        "clientTag": client_tag,
        "apiVersion": api_version,
    }
    response_profile = kwargs.get("response_profile")
    if response_profile:
        data["responseProfile"] = response_profile
    response = _session.post(
        f"{static.get_ott_base()}api_v3/service/asset/action/list",
        params=params,
        json=data,
    )
    total_count = response.json().get("result", {}).get("totalCount", 0)
    if total_count == 0:
        return [], 0
    return response.json()["result"]["objects"], total_count


def get_channel_list(
    _session: Session, ks_token: str, keep_official: bool = True, **kwargs
) -> list:
    """
    Fetches the live channel list from the API

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param keep_official: Whether to send the official query or not
    :param kwargs: Optional arguments
    (official includes the channels that are not available for the user)
    :return: A list of channels
    """
    ksql_addition = ""
    if not keep_official:
        ksql_addition = (
            f" (or entitled_assets='entitledSubscriptions' entitled_assets='free') "
        )
    filter_obj = {
        "kSql": f"(and asset_type='{static.channel_type}'{ksql_addition})",
        # NOTE: (or entitled_assets='entitledSubscriptions' entitled_assets='free') isn't part of the official requests,
        # but it filters out the channels that are not available for the user
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
    }
    # request all channels in 500 per page chunks
    objects = []
    page_idx = 1
    while True:
        result, total_count = filter(_session, filter_obj, ks_token, page_idx, **kwargs)
        objects.extend(result)
        if len(objects) >= total_count:
            break
        page_idx += 1
    return objects


def get_recording_groups(_session: Session, ks_token: str, **kwargs) -> list:
    """
    Fetches the recorded title groups from the API. If its a series,
     it will only return the whole series.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param kwargs: Optional arguments
    :return: A list of recording groups
    """
    filter_obj = {
        "groupBy": [
            {
                "objectType": f"{static.get_ott_platform_name()}AssetMetaOrTagGroupBy",
                "value": "SeriesID",
            }
        ],
        "groupingOptionEqual": "Include",
        "kSql": "(and adult !='1' (and asset_type='recording' start_date <'0' end_date < '-900'))",
        "orderBy": "START_DATE_DESC",
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
    }
    response_profile = {
        "objectType": f"{static.get_ott_platform_name()}OnDemandResponseProfile",
        "relatedProfiles": [
            {
                "objectType": f"{static.get_ott_platform_name()}DetachedResponseProfile",
                "name": "group_result",
                "filter": {
                    "objectType": f"{static.get_ott_platform_name()}AggregationCountFilter"
                },
            }
        ],
    }
    # request all recordings in 20 per page chunks
    objects = []
    page_idx = 1
    while True:
        result, total_count = filter(
            _session,
            filter_obj,
            ks_token,
            page_idx,
            page_size=20,
            response_profile=response_profile,
            **kwargs,
        )
        objects.extend(result)
        if len(objects) >= total_count:
            break
        page_idx += 1
    return objects


def get_recording_titles(
    _session: Session, ks_token: str, media_id: int, **kwargs
) -> list:
    """
    Fetches the recorded titles from the API. Used for series.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param media_id: The media id
    :param kwargs: Optional arguments
    :return: A list of recorded titles
    """
    filter_obj = {
        "kSql": f"(and SeriesId='{media_id}' (and asset_type='recording' start_date <'0' end_date < '0'))",
        "dynamicOrderBy": {
            "objectType": f"{static.get_ott_platform_name()}DynamicOrderBy",
            "name": "EpisodeNumber",
            "orderBy": "META_ASC",
        },
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
    }
    response_profile = {
        "objectType": f"{static.get_ott_platform_name()}OnDemandResponseProfile",
        "relatedProfiles": [
            {
                "objectType": f"{static.get_ott_platform_name()}DetachedResponseProfile",
                "name": "group_result",
                "filter": {
                    "objectType": f"{static.get_ott_platform_name()}AggregationCountFilter"
                },
            }
        ],
    }
    # request all recordings in 20 per page chunks
    objects = []
    page_idx = 1
    while True:
        result, total_count = filter(
            _session,
            filter_obj,
            ks_token,
            page_idx,
            page_size=20,
            response_profile=response_profile,
            **kwargs,
        )
        objects.extend(result)
        if len(objects) >= total_count:
            break
        page_idx += 1
    return objects


def get_movies_page(
    _session: Session,
    ks_token: str,
    movie_id: int,
    page_idx: int,
    page_size: int = 20,
    **kwargs,
) -> list:
    """
    Fetches the movies page from the API. Method can also be used to fetch documentaries
     and other single title categories. Specify the media id accordingly.

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param movie_id: The movie category id
    :param page_idx: The page index
    :param page_size: The page size
    :param kwargs: Optional arguments
    :return: A list of movies
    """
    filter_obj = {
        "kSql": "(and adult !='1' start_date>'-604801' end_date < '0')",
        "groupBy": [
            {
                "objectType": f"{static.get_ott_platform_name()}AssetMetaOrTagGroupBy",
                "value": "Crid",
            }
        ],
        "idEqual": movie_id,
        "objectType": f"{static.get_ott_platform_name()}ChannelFilter",
    }
    response_profile = {
        "objectType": f"{static.get_ott_platform_name()}OnDemandResponseProfile",
        "relatedProfiles": [
            {
                "objectType": f"{static.get_ott_platform_name()}DetachedResponseProfile",
                "name": "group_result",
                "filter": {
                    "objectType": f"{static.get_ott_platform_name()}AggregationCountFilter"
                },
            }
        ],
    }
    return filter(
        _session,
        filter_obj,
        ks_token,
        page_idx,
        page_size=page_size,
        response_profile=response_profile,
        **kwargs,
    )


def get_series_page(
    _session: Session,
    ks_token: str,
    series_id: int,
    page_idx: int,
    page_size: int = 20,
    **kwargs,
) -> list:
    """
    Fetches the series page from the API

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param series_id: The series id
    :param page_idx: The page index
    :param page_size: The page size
    :param kwargs: Optional arguments
    :return: A list of series
    """
    filter_obj = {
        "kSql": "(and adult !='1' start_date>'-604801' end_date < '0')",
        "groupBy": [
            {
                "objectType": f"{static.get_ott_platform_name()}AssetMetaOrTagGroupBy",
                "value": "SeriesID",
            }
        ],
        "idEqual": series_id,
        "objectType": f"{static.get_ott_platform_name()}ChannelFilter",
    }
    response_profile = {
        "objectType": f"{static.get_ott_platform_name()}OnDemandResponseProfile",
        "relatedProfiles": [
            {
                "objectType": f"{static.get_ott_platform_name()}DetachedResponseProfile",
                "name": "group_result",
                "filter": {
                    "objectType": f"{static.get_ott_platform_name()}AggregationCountFilter"
                },
            }
        ],
    }
    return filter(
        _session,
        filter_obj,
        ks_token,
        page_idx,
        page_size=page_size,
        response_profile=response_profile,
        **kwargs,
    )


def get_series_titles(
    _session: Session, ks_token: str, series_id: int, **kwargs
) -> list:
    """
    Fetches the series titles from the API

    :param _session: requests.Session object
    :param ks_token: The ks token
    :param series_id: The series id
    :param kwargs: Optional arguments
    :return: A list of series titles
    """
    filter_obj = {
        "dynamicOrderBy": {
            "objectType": f"{static.get_ott_platform_name()}DynamicOrderBy",
            "name": "EpisodeNumber",
            "orderBy": "META_ASC",
        },
        "kSql": f"(and SeriesId='{series_id}' (or start_date>'-604800' Popular='1'))",
        "typeIn": "0",
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
    }
    response_profile = {
        "objectType": f"{static.get_ott_platform_name()}OnDemandResponseProfile",
        "relatedProfiles": [
            {
                "objectType": f"{static.get_ott_platform_name()}DetachedResponseProfile",
                "name": "group_result",
                "filter": {
                    "objectType": f"{static.get_ott_platform_name()}AggregationCountFilter"
                },
            }
        ],
        "retrievedProperties": "assetId, assetType, duration, finishedWatching, position, watchedDate, mediaFiles,description,objectType,name,id,images,tags,metas,epgChannelId,enableCatchUp,enableCdvr,enableStartOver,enableTrickPlay,linearAssetId,type,updateDate,externalId,epgId,endDate,createDate,crid,startDate",
    }
    # request all recordings in 20 per page chunks
    objects = []
    page_idx = 1
    while True:
        result, total_count = filter(
            _session,
            filter_obj,
            ks_token,
            page_idx,
            page_size=20,
            response_profile=response_profile,
            **kwargs,
        )
        objects.extend(result)
        if len(objects) >= total_count:
            break
        page_idx += 1
    return objects


def get_media_by_id(_session: Session, ks_token: str, media_id: int, **kwargs) -> dict:
    """
    Returns a single media object by id if found, otherwise None

    :param _session: requests session object
    :param ks_token: ks token
    :param media_id: media id
    :param kwargs: optional arguments
    :return: media object or None
    """
    filter_obj = {
        "kSql": f"(and media_id:'{media_id}')",
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
    }
    filtered_objects, _ = filter(
        _session, filter_obj, ks_token, page_idx=1, page_size=1, **kwargs
    )
    return next(iter(filtered_objects or []), None)


def get_epg_by_linear_asset(
    _session: Session,
    ks_token: str,
    linear_asset_id: int,
    start_date: int,
    end_date: int,
    **kwargs,
) -> dict:
    """
    Grabs the entire program guide for a given linear asset id

    :param _session: requests session object
    :param ks_token: ks token
    :param linear_asset_id: linear asset id
    :param start_date: start date (UNIX timestamp)
    :param end_date: end date (UNIX timestamp)
    :param kwargs: optional arguments
    :return: program guide object
    """
    filter_obj = {
        "kSql": f"(and linear_media_id:'{linear_asset_id}' (and start_date >= '{start_date}' end_date  <= '{end_date}') asset_type='epg' auto_fill= true)",
        "objectType": f"{static.get_ott_platform_name()}SearchAssetFilter",
        "orderBy": "START_DATE_ASC",
    }
    # request all recordings in 500 per page chunks
    objects = []
    page_idx = 1
    while True:
        result, total_count = filter(
            _session,
            filter_obj,
            ks_token,
            page_idx,
            page_size=500,
            **kwargs,
        )
        objects.extend(result)
        if len(objects) >= total_count:
            break
        page_idx += 1
    return objects
