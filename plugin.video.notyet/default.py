from json import dumps
from random import choice
from sys import argv
from time import time
from urllib.parse import parse_qsl, quote, urlencode
from uuid import uuid4

import inputstreamhelper  # type: ignore
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from requests import Session
from resources.lib.utils import static as utils_static
from resources.lib.utils import unix_to_date
from resources.lib.yeti import household, login, media_list, misc, playback
from resources.lib.yeti.static import drm_client_tag, get_drm_referrer

addon = xbmcaddon.Addon()
addon_name = addon.getAddonInfo("name")


def add_item(plugin_prefix, handle, name, action, is_directory, **kwargs):
    """
    Adds an item to the Kodi listing
    """
    url = f"{plugin_prefix}?action={action}&name={quote(name)}"
    item = xbmcgui.ListItem(label=name)
    info_labels = {}
    if kwargs.get("description"):
        url += "&descr=%s" % (quote(kwargs["description"]))
        info_labels.update({"plot": kwargs["description"]})
    arts = {}
    if kwargs.get("icon"):
        url += "&icon=%s" % (quote(kwargs["icon"]))
        arts.update({"thumb": kwargs["icon"], "icon": kwargs["icon"]})
    if kwargs.get("fanart"):
        url += "&fanart=%s" % (quote(kwargs["fanart"]))
        arts.update({"fanart": kwargs["fanart"]})
        item.setProperty("Fanart_Image", kwargs["fanart"])
    if kwargs.get("type"):
        info_labels.update({"mediatype": kwargs["type"]})
    if kwargs.get("id"):
        url += "&id=%s" % (kwargs["id"])
    if kwargs.get("year"):
        info_labels.update({"year": kwargs["year"]})
        url += "&year=%s" % (kwargs["year"])
    if kwargs.get("episode"):
        info_labels.update({"episode": kwargs["episode"]})
        url += "&episode=%s" % (kwargs["episode"])
    if kwargs.get("season"):
        info_labels.update({"season": kwargs["season"]})
        url += "&season=%s" % (kwargs["season"])
    if kwargs.get("show_name"):
        info_labels.update({"tvshowtitle": kwargs["show_name"]})
        url += "&show_name=%s" % (quote(kwargs["show_name"]))
    if kwargs.get("genre"):
        info_labels.update({"genre": kwargs["genre"]})
        url += "&genre=%s" % (quote(dumps(kwargs["genre"])))
    if kwargs.get("country"):
        info_labels.update({"country": kwargs["country"]})
        url += "&country=%s" % (quote(dumps(kwargs["country"])))
    if kwargs.get("director"):
        info_labels.update({"director": kwargs["director"]})
        url += "&director=%s" % (quote(dumps(kwargs["director"])))
    if kwargs.get("cast"):
        info_labels.update({"cast": kwargs["cast"]})
        url += "&cast=%s" % (quote(dumps(kwargs["cast"])))
    if kwargs.get("mpaa"):
        info_labels.update({"mpaa": kwargs["mpaa"]})
        url += "&mpaa=%s" % (quote(kwargs["mpaa"]))
    if kwargs.get("extra"):
        url += "&extra=%s" % (kwargs["extra"])
    if kwargs.get("is_livestream"):
        # see https://forum.kodi.tv/showthread.php?pid=2743328#pid2743328 to understand this hack
        # useful for livestreams to not to mark the item as watched + adds switch to channel context menu item
        # NOTE: MUST BE THE LAST PARAMETER in the URL
        url += "&pvr=.pvr"
    if not is_directory:
        item.setProperty("IsPlayable", "true")
    item.setArt(arts)
    item.setInfo(type="Video", infoLabels=info_labels)
    try:
        item.setContentLookup(False)
    except:
        pass  # if it's a local dir, no need for it
    ctx_menu = []
    if kwargs.get("refresh"):
        ctx_menu.append((addon.getLocalizedString(30026), "Container.Refresh"))
    if kwargs.get("ctx_menu"):
        ctx_menu.extend(kwargs["ctx_menu"])
    item.addContextMenuItems(ctx_menu)
    xbmcplugin.addDirectoryItem(int(handle), url, item, is_directory)


def gen_random_device_id(length: int = 16) -> str:
    """
    Generate a random device id of the given length.
    Contains only digits and numbers. i.e., C8027D41A20BC0C7

    :param length: The length of the device id to generate.
    :return: The generated device id.
    """
    from string import ascii_uppercase, digits

    # import only used here so it's fine to import here

    return "".join(choice(ascii_uppercase + digits) for _ in range(length))


def authenticate(session: Session):
    """
    Method to be called to check authentication state. If not authenticated, it will
    handle the entire authentication process including OAuth login and KS token retrieval as
    well as storing the tokens in the addon settings and device registration.
    If already authenticated, it will check if the KS token is still valid and if not, it will
    retrieve a new one.

    OAuth token refresh is not implemented yet.

    :param session: The requests session to use for the authentication.
    :return: None
    """
    if not all([addon.getSetting("username"), addon.getSetting("password")]):
        return
    if not addon.getSetting("devicekey"):
        device_id = gen_random_device_id()
        addon.setSetting("devicekey", device_id)
    ks_expiry = addon.getSetting("ksexpiry")

    if ks_expiry and int(ks_expiry) > int(time()):
        return  # KS token is valid so no need to reauthenticate
    user_agent = addon.getSetting("useragent")

    # OAuth login
    # NOTE: while we store the OAuth access token, there is
    # no session renewal implemented yet
    current_time = int(time())
    expires = addon.getSetting("oauthexpires")
    prog_dialog = xbmcgui.DialogProgress()
    prog_dialog.create(addon_name)
    # obtain new OAuth access token only if it expired and we don't
    # have a ks token yet or if it doesn't exist
    if not expires or (
        (expires and int(expires) > current_time) and not addon.getSetting("kstoken")
    ):
        prog_dialog.update(50, addon.getLocalizedString(30027))
        try:
            access_token, refresh_token, expires_in = login.login(
                session,
                device_id,
                addon.getSetting("username"),
                addon.getSetting("password"),
                user_agent=user_agent,
                app_version=addon.getSetting("appversion"),
                client_tag=addon.getSetting("clienttag"),
                partner_id=addon.getSetting("partnerid"),
                platform=addon.getSetting("platform"),
                device_family=addon.getSetting("devicefamily"),
                device_brand=addon.getSetting("devicebrand"),
                firmware=addon.getSetting("firmware"),
                tv_pil_version=addon.getSetting("tvpilversion"),
                realm=addon.getSetting("realm"),
            )
        except login.LoginFailed as e:
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, str(e))
            return
        addon.setSetting("oauthaccesstoken", access_token)
        addon.setSetting("oauthrefreshtoken", refresh_token)
        addon.setSetting("oauthexpires", str(current_time + expires_in))
    # KS login
    # refresh KS token if it expired
    if ks_expiry and int(ks_expiry) < current_time:
        prog_dialog.update(85, addon.getLocalizedString(30028))
        try:
            ks_token, ks_refresh_token, ks_expiry = login.refresh_ks_token(
                session,
                addon.getSetting("kstoken"),
                addon.getSetting("ksrefreshtoken"),
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
            )
        except login.RefreshSessionFailed as e:
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, str(e))
            return
        addon.setSetting("kstoken", ks_token)
        addon.setSetting("ksrefreshtoken", ks_refresh_token)
        addon.setSetting("ksexpiry", str(ks_expiry))
    # obtain new KS token if it doesn't exist
    if not addon.getSetting("kstoken"):
        prog_dialog.update(65, addon.getLocalizedString(30029))
        # anonymous login
        anon_ks_token, _, _ = login.anonymous_login(
            session,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
            partner_id=addon.getSetting("partnerid"),
        )
        prog_dialog.update(75, addon.getLocalizedString(30030))
        # login using the OAuth access token and anonymous KS token
        try:
            ks_token, ks_refresh_token, ks_expiry = login.login_ott(
                session,
                access_token,
                anon_ks_token,
                device_id,
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
                partner_id=addon.getSetting("partnerid"),
                ott_password=addon.getSetting("ottpassword"),
                ott_username=addon.getSetting("ottusername"),
            )
        except login.LoginFailed as e:
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, str(e))
            return
        prog_dialog.update(85, addon.getLocalizedString(30031))
        # register device or get device id if already registered
        try:
            got_device_id = login.get_or_add_device_to_household(
                session,
                ks_token,
                device_id,
                name=addon.getSetting("devicenick"),
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
                device_brand=addon.getSetting("devicebrand"),
            )
            assert got_device_id == device_id
        except AssertionError:
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, addon.getLocalizedString(30032))
            return
        except login.AddHouseHoldDeviceError as e:
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, str(e))
            return
        addon.setSetting("kstoken", ks_token)
        addon.setSetting("ksrefreshtoken", ks_refresh_token)
        addon.setSetting("ksexpiry", str(ks_expiry))
        prog_dialog.update(95, addon.getLocalizedString(30072))
        # get household id and user id
        # used later for playback stats
        household_obj = household.get_household(
            session,
            ks_token,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
        household_id = household_obj.get("id", -1)
        addon.setSetting("householdid", str(household_id))
        user_id = next(
            (user.get("id") for user in household_obj.get("users", [])),
            -1,
        )
        addon.setSetting("userid", str(user_id))
    prog_dialog.close()
    # show notification
    xbmcgui.Dialog().notification(
        addon_name,
        addon.getLocalizedString(30033),
        icon=xbmcgui.NOTIFICATION_INFO,
        time=5000,
    )


def prepare_session() -> Session:
    """
    Prepare a requests session for use within the addon. Also sets
     the user agent to a random desktop user agent if it is not set.

    :return: The prepared session.
    """
    user_agent = addon.getSetting("useragent")
    if not user_agent:
        addon.setSetting("useragent", choice(utils_static.desktop_user_agents))
        user_agent = addon.getSetting("useragent")
    session = Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def main_menu() -> None:
    """
    Renders the main menu of the addon.

    :return: None
    """
    # channel list
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30034),
        action="channel_list",
        is_directory=True,
    )
    # list of recordings (groupped if series)
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30047),
        action="rec_main",
        is_directory=True,
    )
    # add recording
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30125),
        action="rec_add",
        is_directory=True,
    )
    # list of movies
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30065),
        action="movies",
        is_directory=True,
        extra=1,  # page number
    )
    # list of documentaries
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30067),
        action="documentaries",
        is_directory=True,
        extra=1,  # page number
    )
    # list of series
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30068),
        action="series_list",
        is_directory=True,
        extra=1,  # page number
    )
    # list of devices
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30057),
        action="device_list",
        is_directory=True,
    )
    # remove current device id
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30035),
        description=addon.getLocalizedString(30036),
        action="clear_device_key",
        is_directory=True,
    )
    # reset session tokens and relogin
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30037),
        description=addon.getLocalizedString(30038),
        action="clear_settings",
        is_directory=True,
    )
    # settings
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30039),
        description=addon.getLocalizedString(30040),
        action="settings",
        is_directory=True,
    )
    # about
    add_item(
        plugin_prefix=argv[0],
        handle=argv[1],
        name=addon.getLocalizedString(30122),
        action="about",
        is_directory=True,
    )
    xbmcplugin.endOfDirectory(int(argv[1]))


def channel_list(session: Session) -> None:
    """
    Renders the list of live channels.

    :param session: The requests session.
    :return: None
    """
    channels = media_list.get_channel_list(
        session,
        addon.getSetting("kstoken"),
        addon.getSettingBool("listofficial"),
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    if addon.getSettingBool("sortabc"):
        channels.sort(key=lambda channel: channel.get("name"))
    hide_adult = addon.getSettingBool("hideadult")
    for channel in channels:
        channel_id = channel.get("id")
        if not channel_id:
            continue
        name = channel.get("name")
        images = channel.get("images")
        is_adult = channel.get("metas", {}).get("Adult", {}).get("value", False)
        if is_adult:
            if hide_adult:
                continue
            name += " ([COLOR red]18+[/COLOR])"
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/width/240"
                # NOTE: not used in official apps, but renders well in Kodi
            )
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            action="play_channel",
            is_directory=False,
            id=channel_id,
            icon=image,
            is_livestream=True,
            refresh=True,
        )
    xbmcplugin.endOfDirectory(int(argv[1]))
    xbmcplugin.setContent(int(argv[1]), "videos")


def _gen_mgr_params(playback_type: str, playback_obj: list) -> str:
    """
    Generates the parameters for playback manager's statistics report.

    :param playback_type: playback type
    :param playback_obj: playback object
    :return: parameters for playback manager
    """
    try:
        params = {}
        if playback_type == "recording":
            params["type"] = "recording"
            params["context"] = "PLAYBACK"
            params["id"] = playback_obj[0]["recordingId"]
            params["fileId"] = playback_obj[1]["sources"][0]["id"]
            params["programId"] = playback_obj[0]["epgId"]
        elif playback_type == "epg":
            params["type"] = "epg"
            params["context"] = "CATCHUP"
            params["id"] = playback_obj[0]["id"]
            params["fileId"] = playback_obj[1]["sources"][0]["id"]
            params["programId"] = playback_obj[0]["epgId"]
        else:
            params["type"] = "media"
            params["context"] = "PLAYBACK"
            params["id"] = playback_obj[0]["id"]
            params["fileId"] = playback_obj[1]["sources"][0]["id"]
            params["programId"] = 0  # NOTE: would need another request to get this
    except (KeyError, IndexError) as e:
        return ""
    return urlencode(params)


def play(session: Session, media_id: int, extra: str, title: str, icon: str) -> None:
    """
    Plays the media.

    :param session: The requests session.
    :param media_id: The media id.
    :param extra: The extra parameter.
    :param title: The title of the media.
    :param icon: The icon of the media.
    :return: None
    """
    # recording
    if extra == "recording":
        playback_obj = playback.get_playback_obj(
            session,
            addon.getSetting("kstoken"),
            media_id,
            asset_reference_type="npvr",
            asset_type="recording",
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    # movie/series/documentary from the catalog
    elif extra == "epg":
        playback_obj = playback.get_playback_obj(
            session,
            addon.getSetting("kstoken"),
            media_id,
            asset_reference_type="epg_internal",
            asset_type="epg",
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    # live channel
    else:
        playback_obj = playback.get_playback_obj(
            session,
            addon.getSetting("kstoken"),
            media_id,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    # check if entitled (messages list has a message with code NotEntitled)
    if len(playback_obj) > 1 and any(
        message.get("code") == "NotEntitled"
        for message in playback_obj[1].get("messages", [])
    ):
        xbmcgui.Dialog().ok(addon_name, addon.getLocalizedString(30041))
        return
    # check if concurrent streams limit reached (no stream URL then)
    if len(playback_obj) > 1 and any(
        message.get("code") == "ConcurrencyLimitation"
        for message in playback_obj[1].get("messages", [])
    ):
        xbmcgui.Dialog().ok(addon_name, addon.getLocalizedString(30076))
        return
    # construct 'trailer' parameters for playback manager
    trailer_params = _gen_mgr_params(extra, playback_obj)
    # get the first stream object
    playback_obj = next(
        (obj["sources"] for obj in playback_obj if obj.get("sources")), None
    )
    if not playback_obj:
        xbmcgui.Dialog().ok(addon_name, addon.getLocalizedString(30042))
        return
    playback_obj = playback_obj[0]
    license_url = None
    if playback_obj.get("type") == "DASH_WV":
        # get first the first entry with scheme=WIDEVINE_CENC from the drm list
        drm = next(
            (
                drm
                for drm in playback_obj.get("drm", [])
                if drm.get("scheme") == "WIDEVINE_CENC"
            ),
            None,
        )
        if not drm:
            xbmcgui.Dialog().ok(
                addon_name,
                addon.getLocalizedString(30043),
            )
            return
        license_url = drm.get("licenseURL")
        if license_url:
            license_url += (
                f"&sessionId="
                + f"{uuid4()}:{uuid4()}"
                + "&clientTag="
                + drm_client_tag
                + "&referrer="
                + quote(get_drm_referrer())
            )
    # query string not required, but original does it too
    manifest_url = playback_obj.get("url") + "&response=200&bk-ml=1"
    # manifest is a 200 with a Location header, we must query it ourselves
    # Kodi's player doesn't work out of the box
    response = session.get(manifest_url, allow_redirects=False)
    manifest_url = response.headers.get("Location")
    if not manifest_url:
        xbmcgui.Dialog().ok(addon_name, addon.getLocalizedString(30044))
        return
    # construct playback item
    is_helper = inputstreamhelper.Helper("mpd", drm="com.widevine.alpha")
    play_item = xbmcgui.ListItem(path=manifest_url)
    # not a trailer, but hack for the keepalive handler to know
    # that the stream is ours
    if not trailer_params:
        # show notification that we won't report statistics back
        xbmcgui.Dialog().notification(
            addon_name,
            addon.getLocalizedString(30075),
            xbmcgui.NOTIFICATION_WARNING,
            3000,
        )
    play_item.setInfo(
        "video", {"trailer": argv[0] + "?" + trailer_params, "title": title}
    )
    if icon:
        play_item.setArt({"thumb": icon})
    play_item.setContentLookup(False)
    play_item.setMimeType("application/dash+xml")
    play_item.setProperty("inputstream", is_helper.inputstream_addon)
    play_item.setProperty("inputstream.adaptive.manifest_type", "mpd")
    play_item.setProperty(
        "inputstream.adaptive.manifest_headers",
        urlencode({"User-Agent": addon.getSetting("useragent")}),
    )
    # if DRM protected, set license URL
    if license_url:
        if not is_helper.check_inputstream():
            xbmcgui.Dialog().ok(addon_name, addon.getLocalizedString(30045))
            return
        play_item.setProperty("inputstream.adaptive.license_type", "com.widevine.alpha")
        play_item.setProperty(
            "inputstream.adaptive.license_key",
            license_url
            + "|"
            + urlencode(
                {
                    "User-Agent": addon.getSetting("useragent"),
                    "Content-Type": "application/json",
                    # without the content-type header we get a 500 error
                    # even though the request isn't json
                }
            )
            + "|R{SSM}|",
        )
    xbmcplugin.setResolvedUrl(int(argv[1]), True, listitem=play_item)


def recording_listing(session: Session, media_id: int = None) -> None:
    """
    List recordings in groups. If entry is a movie or a single episode, assign playback action.
    Otherwise, another listing is created for the group.

    :param session: requests session
    :param media_id: media ID to list recordings for
    :return: None
    """
    if media_id:
        recordings = media_list.get_recording_titles(
            session,
            addon.getSetting("kstoken"),
            media_id,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    else:
        recordings = media_list.get_recording_groups(
            session,
            addon.getSetting("kstoken"),
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    for recording in recordings:
        title_id = recording.get("recordingId")
        if not title_id:
            continue
        name = recording.get("name")
        description = recording.get("description")
        images = recording.get("images")
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/height/360/width/640"
                # optimal size for Kodi
            )
        metas = recording.get("metas", {})
        year = metas.get("Year", {}).get("value")
        rec_type = recording.get("recordingType").lower()
        content_type = metas.get("ContentType", {}).get("value")
        episode = None
        season = None
        if (
            rec_type.lower() == "single"
            and content_type.lower() == "series"
            or media_id
        ):
            episode = metas.get("EpisodeNumber", {}).get("value")
            season = metas.get("SeasonNumber", {}).get("value")
            name = metas.get("EpisodeName", {}).get("value", name)
            if episode and season:
                name += f" [B]S{season}E{episode}[/B]"
        tags = recording.get("tags", {})
        genres = [
            g.get("value").strip() for g in tags.get("Genre", {}).get("objects", [])
        ]
        pg_rating = next(
            (g.get("value") for g in tags.get("ParentalRating", {}).get("objects", [])),
            None,
        )
        countries = [g.get("value") for g in tags.get("Country", {}).get("objects", [])]
        directors = []
        actors = []
        ctx_menu = []
        if media_id or rec_type != "series":
            directors = [
                g.get("value") for g in tags.get("Director", {}).get("objects", [])
            ]
            actors = [g.get("value") for g in tags.get("Actors", {}).get("objects", [])]
            start_date = unix_to_date(recording.get("startDate", 0))
            end_date = unix_to_date(recording.get("endDate", 0))
            expires = unix_to_date(recording.get("viewableUntilDate", 0))
            description += f"\n{addon.getLocalizedString(30052)}: {start_date}"
            description += f"\n{addon.getLocalizedString(30053)}: {end_date}"
            description += f"\n{addon.getLocalizedString(30054)}: {expires}"
            action = "play_channel"
            ctx_menu.append(
                (
                    addon.getLocalizedString(30048),
                    f"RunPlugin({argv[0]}?action=del_rec&id={title_id})",
                )
            )
        else:
            action = "rec_titles"
            title_id = metas.get("SeriesID", {}).get("value")
            name += "\n[B]>>[/B]"
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            action=action,
            is_directory=True if action == "rec_titles" else False,
            icon=image,
            description=description,
            year=year,
            type=rec_type,
            id=title_id,
            genre=genres,
            mpaa=pg_rating,
            episode=episode,
            season=season,
            show_name=name,
            country=countries,
            director=directors,
            cast=actors,
            refresh=True,
            ctx_menu=ctx_menu,
            extra="recording",
        )
    xbmcplugin.endOfDirectory(int(argv[1]))
    xbmcplugin.setContent(int(argv[1]), "episodes" if media_id else "tvshows")


def add_recording(session: Session) -> None:
    """
    Get an ID back from the user and try to record it.

    :param session: requests session
    :return: None
    """
    # show a numeric dialog to get the ID
    dialog = xbmcgui.Dialog()
    user_input = dialog.numeric(0, addon.getLocalizedString(30126))
    if not user_input:
        return
    # try to record the ID
    try:
        recording = misc.create_single_recording(
            session,
            addon.getSetting("kstoken"),
            user_input,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
    except misc.RecordingCreationError as e:
        if e.code == "4024":
            # InvalidAssetId
            dialog.ok(addon_name, addon.getLocalizedString(30128))
        elif e.code == "3035":
            # ProgramCdvrNotEnabled
            dialog.ok(addon_name, addon.getLocalizedString(30129))
        else:
            dialog.ok(addon_name, str(e))
        return
    status = recording.get("status")
    if status in ["RECORDING", "SCHEDULED"]:
        dialog.ok(addon_name, addon.getLocalizedString(30127))
    elif status == "RECORDED":
        dialog.ok(addon_name, addon.getLocalizedString(30131))
    else:
        dialog.ok(addon_name, addon.getLocalizedString(30051).format(response=status))


def movies_listing(session: Session, action: str, movie_id: int, page: int) -> None:
    """
    List movies.

    :param session: requests session
    :param action: action to take when movie is selected
    :param movie_id: movie ID to list movies for
    :param page: page number to list
    :return: None
    """
    movies, total_count = media_list.get_movies_page(
        session,
        addon.getSetting("kstoken"),
        movie_id,
        page,
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    for movie in movies:
        media_id = movie.get("id")
        if not media_id:
            continue
        name = movie.get("name")
        enable_catchup = movie.get("enableCatchUp")
        if not enable_catchup:
            name = f"[COLOR=red]{name}[/COLOR]"
        description = movie.get("description")
        images = movie.get("images")
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/height/360/width/640"
                # optimal size for Kodi
            )
        metas = movie.get("metas", {})
        year = metas.get("Year", {}).get("value")
        tags = movie.get("tags", {})
        genres = [
            g.get("value").strip() for g in tags.get("Genre", {}).get("objects", [])
        ]
        pg_rating = next(
            (g.get("value") for g in tags.get("ParentalRating", {}).get("objects", [])),
            None,
        )
        countries = [g.get("value") for g in tags.get("Country", {}).get("objects", [])]
        directors = [
            g.get("value") for g in tags.get("Director", {}).get("objects", [])
        ]
        actors = [g.get("value") for g in tags.get("Actors", {}).get("objects", [])]
        is_series = metas.get("IsSeries", {}).get("value")
        episode = None
        season = None
        if is_series == "true":
            episode = metas.get("EpisodeNumber", {}).get("value")
            season = metas.get("SeasonNumber", {}).get("value")
            name = metas.get("EpisodeName", {}).get("value", name)
            if episode and season:
                name += f" [B]S{season}E{episode}[/B]"
            elif episode:
                name += f" [B]E{episode}[/B]"
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            action="play_channel",
            is_directory=False,
            icon=image,
            description=description,
            year=year,
            id=media_id,
            genre=genres,
            mpaa=pg_rating,
            country=countries,
            director=directors,
            cast=actors,
            refresh=True,
            extra="epg",
        )
    # check if there are more pages
    if total_count > (page + 1) * 20:  # TODO: don't hardcode page size
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=addon.getLocalizedString(30066),
            action=action,
            is_directory=True,
            extra=page + 1,
        )
    xbmcplugin.endOfDirectory(int(argv[1]))
    if action == "movies":
        xbmcplugin.setContent(int(argv[1]), "movies")
    elif action == "documentaries":
        xbmcplugin.setContent(int(argv[1]), "tvshows")


def series_listing(session: Session, page: int) -> None:
    """
    List series.

    :param session: requests session
    :param page: page number to list
    :return: None
    """
    series, total_count = media_list.get_series_page(
        session,
        addon.getSetting("kstoken"),
        358054,  # TODO: don't hardcode this
        page,
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    for serie in series:
        metas = serie.get("metas", {})
        series_id = metas.get("SeriesID", {}).get("value")
        if not series_id:
            continue
        name = serie.get("name")
        description = serie.get("description")
        images = serie.get("images")
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/height/360/width/640"
                # optimal size for Kodi
            )
        year = metas.get("Year", {}).get("value")
        tags = serie.get("tags", {})
        genres = [
            g.get("value").strip() for g in tags.get("Genre", {}).get("objects", [])
        ]
        pg_rating = next(
            (g.get("value") for g in tags.get("ParentalRating", {}).get("objects", [])),
            None,
        )
        countries = [g.get("value") for g in tags.get("Country", {}).get("objects", [])]
        directors = [
            g.get("value") for g in tags.get("Director", {}).get("objects", [])
        ]
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            action="series_episodes",
            is_directory=True,
            icon=image,
            description=description,
            year=year,
            id=series_id,
            genre=genres,
            mpaa=pg_rating,
            country=countries,
            director=directors,
            refresh=True,
            extra="1",
        )
    # check if there are more pages
    if total_count > (page + 1) * 20:  # TODO: don't hardcode page size
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=addon.getLocalizedString(30066),
            action="series_list",
            is_directory=True,
            extra=page + 1,
        )
    xbmcplugin.endOfDirectory(int(argv[1]))
    xbmcplugin.setContent(int(argv[1]), "tvshows")


def series_episodes(session: Session, media_id: int) -> None:
    """
    List series episodes.

    :param session: requests session
    :param media_id: series id
    :return: None
    """
    episodes = media_list.get_series_titles(
        session,
        addon.getSetting("kstoken"),
        media_id,
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    episodes = sorted(
        episodes,
        key=lambda x: (
            int(x.get("metas", {}).get("SeasonNumber", {}).get("value", 0)),
            int(x.get("metas", {}).get("EpisodeNumber", {}).get("value", 0)),
            x.get("startDate"),
        ),
    )
    for episode in episodes:
        name = episode.get("name")
        description = episode.get("description")
        images = episode.get("images")
        episode_id = episode.get("id")
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/height/360/width/640"
                # optimal size for Kodi
            )
        metas = episode.get("metas", {})
        ep_number = metas.get("EpisodeNumber", {}).get("value")
        season = metas.get("SeasonNumber", {}).get("value")
        name = metas.get("EpisodeName", {}).get("value", name)
        enable_catchup = episode.get("enableCatchUp")
        if not enable_catchup:
            name = f"[COLOR=red]{name}[/COLOR]"
        if ep_number and season:
            name += f" [B]S{season}E{ep_number}[/B]"
        elif ep_number:
            name += f" [B]E{ep_number}[/B]"
        action = "play_channel"
        if episode.get("startDate") > time():
            name = f"[COLOR=yellow]{name}[/COLOR] ({addon.getLocalizedString(30069)}: {unix_to_date(episode.get('startDate'))})"
            # for some reason the API would return a manifest URL
            # but it 404s when trying to play it
            # (as the episode will be broadcasted in the future)
            action = "dummy"
        year = metas.get("Year", {}).get("value")
        tags = episode.get("tags", {})
        genres = [
            g.get("value").strip() for g in tags.get("Genre", {}).get("objects", [])
        ]
        pg_rating = next(
            (g.get("value") for g in tags.get("ParentalRating", {}).get("objects", [])),
            None,
        )
        countries = [g.get("value") for g in tags.get("Country", {}).get("objects", [])]
        directors = [
            g.get("value") for g in tags.get("Director", {}).get("objects", [])
        ]
        actors = [g.get("value") for g in tags.get("Actors", {}).get("objects", [])]
        start_date = unix_to_date(episode.get("startDate", 0))
        end_date = unix_to_date(episode.get("endDate", 0))
        expires = unix_to_date(episode.get("viewableUntilDate", 0))
        description += f"\n{addon.getLocalizedString(30052)}: {start_date}"
        description += f"\n{addon.getLocalizedString(30053)}: {end_date}"
        description += f"\n{addon.getLocalizedString(30054)}: {expires}"
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            action=action,
            is_directory=False,
            icon=image,
            description=description,
            year=year,
            id=episode_id,
            genre=genres,
            mpaa=pg_rating,
            country=countries,
            director=directors,
            cast=actors,
            refresh=True,
            extra="epg",
        )
    xbmcplugin.endOfDirectory(int(argv[1]))
    xbmcplugin.setContent(int(argv[1]), "episodes")


def delete_recording(session: Session, media_id: int) -> None:
    """
    Delete a recording.

    :param session: requests session
    :param media_id: recording id
    :return: None
    """
    dialog = xbmcgui.Dialog()
    if dialog.yesno(addon_name, addon.getLocalizedString(30049)):
        try:
            result = misc.delete_recording(
                session,
                addon.getSetting("kstoken"),
                media_id,
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
            )
        except misc.RecordingDeletionError as e:
            dialog.ok(addon_name, str(e))
            return
        if result == "DELETED":
            dialog.ok(addon_name, addon.getLocalizedString(30050))
        else:
            dialog.ok(
                addon_name, addon.getLocalizedString(30051).format(response=result)
            )
        xbmc.executebuiltin("Container.Refresh")


def device_list(session: Session) -> None:
    """
    List devices.

    :param session: requests session
    :return: None
    """
    # local import should be fine
    # since it's not used often
    from resources.lib.yeti import devices

    # request device list
    device_list, _ = devices.get_devices(
        session,
        addon.getSetting("kstoken"),
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    # sort by lastActivityTime descending
    device_list.sort(key=lambda x: x.get("lastActivityTime", 0), reverse=True)
    # request currently streaming devices
    streaming_devices, _ = devices.get_streaming_devices(
        session,
        addon.getSetting("kstoken"),
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    # create a lookup table for brands
    brand_lookup = devices.get_brands(
        session,
        addon.getSetting("kstoken"),
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    for device in device_list:
        brand_id = device.get("brandId")
        brand = brand_lookup.get(brand_id, "unknown")
        name = device.get("name")
        if not name:
            name = brand
        else:
            name = f"{name} ({brand})"
        device_id = device.get("udid")
        if device_id == addon.getSetting("devicekey"):
            name += f" [{addon.getLocalizedString(30064)}]"
        activated_on = unix_to_date(device.get("activatedOn", 0))
        last_activity = unix_to_date(device.get("lastActivityTime", 0))
        household = device.get("householdId")
        state = device.get("state")
        description = (
            f"{addon.getLocalizedString(30011)}: {device_id}\n"
            f"{addon.getLocalizedString(30058)}: {activated_on}\n"
            f"{addon.getLocalizedString(30059)}: {last_activity}\n"
            f"{addon.getLocalizedString(30060)}: {household}\n"
            f"{addon.getLocalizedString(30061)}: {state}"
        )
        asset_id, asset_type = next(
            (
                (
                    streaming_device.get("asset", {}).get("id"),
                    streaming_device.get("asset", {}).get("type"),
                )
                for streaming_device in streaming_devices
                if streaming_device.get("udid") == device.get("udid")
            ),
            (None, None),
        )
        if asset_id:
            name = f"[COLOR=red]{addon.getLocalizedString(30073)} | {name}[/COLOR]"
            media = media_list.get_media_by_id(
                session,
                addon.getSetting("kstoken"),
                asset_id,
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
            )
            if media:
                name += f" - {media.get('name')}"
                description += (
                    f"\n{addon.getLocalizedString(30073)}: {media.get('name')}"
                    f"\n{addon.getLocalizedString(30074)}: {asset_type}"
                )
        ctx_menu = [
            (
                addon.getLocalizedString(30062),
                f"RunPlugin({argv[0]}?action=del_device&device_id={device_id})",
            )
        ]
        add_item(
            plugin_prefix=argv[0],
            handle=argv[1],
            name=name,
            description=description,
            ctx_menu=ctx_menu,
            refresh=True,
            action="dummy",  # clicking should do nothing
            is_directory=True,
        )
    xbmcplugin.endOfDirectory(int(argv[1]))


def delete_device(session: Session, device_id: str) -> None:
    """
    Delete a device permanently.

    :param session: requests session
    :param device_id: device id
    :return: None
    """
    from resources.lib.yeti import devices

    dialog = xbmcgui.Dialog()
    if dialog.yesno(addon_name, addon.getLocalizedString(30063)):
        try:
            result = devices.delete_device(
                session,
                addon.getSetting("kstoken"),
                device_id,
                api_version=addon.getSetting("apiversion"),
                client_tag=addon.getSetting("clienttag"),
            )
        except devices.DeviceDeletionError as e:
            dialog.ok(addon_name, str(e))
            return
        if result == True:
            if addon.getSetting("devicekey") == device_id:
                addon.setSetting("devicekey", "")
                clear_settings()
            dialog.ok(addon_name, addon.getLocalizedString(30050))
        else:
            dialog.ok(
                addon_name, addon.getLocalizedString(30051).format(response=result)
            )
        xbmc.executebuiltin("Container.Refresh")


def clear_settings() -> None:
    """
    Clear all stored tokens.

    :return: None
    """
    addon.setSetting("oauthaccesstoken", "")
    addon.setSetting("oauthrefreshtoken", "")
    addon.setSetting("oauthexpires", "")
    addon.setSetting("kstoken", "")
    addon.setSetting("ksrefreshtoken", "")
    addon.setSetting("ksexpiry", "")
    addon.setSetting("useragent", "")


def reset_device_key(session: Session) -> None:
    """
    Reset the device key.

    :param session: requests session
    :return: None
    """
    # local import should be fine
    # since it's not used often
    from resources.lib.yeti import devices

    old_device_key = addon.getSetting("devicekey")
    dialog = xbmcgui.Dialog()
    if dialog.yesno(addon_name, addon.getLocalizedString(30063)):
        addon.setSetting("devicekey", "")
        clear_settings()
        prepare_session()
        authenticate(session)
        try:
            result = devices.delete_device(
                session, addon.getSetting("kstoken"), old_device_key
            )
        except devices.DeviceDeletionError as e:
            dialog.ok(addon_name, str(e))
            return
        if result == True:
            dialog.ok(addon_name, addon.getLocalizedString(30050))
        else:
            dialog.ok(
                addon_name, addon.getLocalizedString(30051).format(response=result)
            )
        xbmc.executebuiltin("Container.Refresh")


def update_epg(_session: Session) -> None:
    """
    Update the EPG file manually.

    :param _session: requests session
    :return: None
    """
    # local import should be fine
    # since it's not used often
    from export_data import days_to_seconds, export_epg, int_to_time

    # get epg settings
    from_time = addon.getSetting("epgfrom")
    to_time = addon.getSetting("epgto")
    dialog = xbmcgui.Dialog()
    if not all([from_time, to_time]):
        dialog.ok(addon_name, addon.getLocalizedString(30099))
        return
    now = int(time())
    from_time = now - days_to_seconds(int(from_time))
    to_time = now + days_to_seconds(int(to_time))
    dialog.notification(
        addon_name,
        f"{addon.getLocalizedString(30100)}: {int_to_time(from_time)} - {int_to_time(to_time)}",
    )
    export_epg(_session, from_time, to_time)


def about_dialog() -> None:
    """
    Show the about dialog.

    :return: None
    """
    dialog = xbmcgui.Dialog()
    dialog.textviewer(
        addon.getAddonInfo("name"),
        addon.getLocalizedString(30121),
    )


if __name__ == "__main__":
    params = dict(parse_qsl(argv[2].replace("?", "")))
    action = params.get("action")
    # session to be used for all requests
    session = prepare_session()
    # authenticate if necessary
    authenticate(session)

    # main router
    if action is None:
        if addon.getSettingBool("isfirstrun"):
            # show about dialog
            about_dialog()
            addon.setSettingBool("isfirstrun", False)
        if not all([addon.getSetting("username"), addon.getSetting("password")]):
            # show dialog to login
            dialog = xbmcgui.Dialog()
            dialog.ok(addon_name, addon.getLocalizedString(30046))
            addon.openSettings()
            exit()
        main_menu()
    elif action == "play_channel":
        play(
            session,
            params.get("id"),
            params.get("extra"),
            params.get("name", ""),
            params.get("icon"),
        )
    elif action == "channel_list":
        channel_list(session)
    elif action == "movies":
        movies_listing(session, params.get("action"), 357915, int(params.get("extra")))
    elif action == "documentaries":
        movies_listing(session, params.get("action"), 358677, int(params.get("extra")))
    elif action == "series_list":
        series_listing(session, int(params.get("extra")))
    elif action == "series_episodes":
        series_episodes(session, params.get("id"))
    elif action == "rec_main":
        recording_listing(session)
    elif action == "rec_titles":
        recording_listing(session, params.get("id"))
    elif action == "rec_add":
        add_recording(session)
    elif action == "del_rec":
        delete_recording(session, params.get("id"))
    elif action == "device_list":
        device_list(session)
    elif action == "del_device":
        delete_device(session, params.get("device_id"))
    elif action == "settings":
        addon.openSettings()
    elif action == "export_chanlist":
        import export_data

        export_data.export_channel_list(session)
        exit()
    elif action == "export_epg":
        update_epg(session)
    elif action == "clear_device_key":
        reset_device_key(session)
    elif action == "clear_settings":
        clear_settings()
        exit()
    elif action == "about":
        about_dialog()
