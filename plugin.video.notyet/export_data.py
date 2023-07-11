import threading
from datetime import datetime
from time import time
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xmltodict  # type: ignore
from default import authenticate
from requests import Session
from resources.lib.yeti import media_list

addon = xbmcaddon.Addon()
handle = "[NotYet]"


def get_path(is_epg: bool = False) -> str:
    """
    Check if the channel and epg path exists

    :param is_epg: Whether to check for the epg path
    :return: The path if it exists
    :raises IOError: If the path does not exist
    """
    path = addon.getSetting("channelexportpath")
    if is_epg:
        name = addon.getSetting("epgexportname")
    else:
        name = addon.getSetting("channelexportname")
    if not all([path, name]):
        return False
    if not xbmcvfs.exists(path):
        result = xbmcvfs.mkdirs(path)
        if not result:
            raise IOError(f"Failed to create directory {path}")
    # NOTE: we trust the user to enter a valid path
    # there is no sanitization
    return xbmcvfs.translatePath(f"{path}/{name}")


def export_channel_list(_session: Session) -> None:
    """
    Export channel list to an m3u file

    :param _session: requests.Session object
    :return: None
    """
    dialog = xbmcgui.Dialog()
    try:
        path = get_path()
    except IOError as e:
        dialog.notification(
            addon.getAddonInfo("name"),
            addon.getLocalizedString(30081),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return
    if not all([addon.getSetting("username"), addon.getSetting("password")]):
        dialog.notification(
            addon.getAddonInfo("name"),
            addon.getLocalizedString(30082),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return
    authenticate(_session)
    # print m3u header
    output = "#EXTM3U\n\n"
    channels = media_list.get_channel_list(
        _session,
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
        name = channel.get("name").strip()
        formatted_name = name
        images = channel.get("images")
        is_adult = channel.get("metas", {}).get("Adult", {}).get("value", False)
        if is_adult:
            if hide_adult:
                continue
            formatted_name += " ([COLOR red]18+[/COLOR])"
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/width/240"
            )
        category = "notyet"
        if is_adult:
            category += ";18+"
        # print channel data to m3u
        output += f'#EXTINF:-1 tvg-id="{channel_id}" tvg-name="{name}" tvg-logo="{image}" group-title="{category}",{formatted_name}\n'
        query = {
            "action": "play_channel",
            "name": formatted_name,
            "icon": image,
            "id": channel_id,
            "pvr": ".pvr",  # hack to make Kodi recognize the stream as a PVR stream
        }
        url = f"plugin://{addon.getAddonInfo('id')}/?{urlencode(query)}"
        output += f"{url}\n\n"
    try:
        with open(path, "w") as f:
            f.write(output)
    except IOError:
        dialog.notification(
            addon.getAddonInfo("name"),
            addon.getLocalizedString(30081),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return
    dialog.notification(
        addon.getAddonInfo("name"),
        addon.getLocalizedString(30083),
        xbmcgui.NOTIFICATION_INFO,
        sound=False,
    )


def unix_to_epg_time(unix_time: int) -> str:
    """
    Convert unix time to EPG time format.

    :param unix_time: Unix time
    :return: EPG time format
    """
    return datetime.utcfromtimestamp(unix_time).strftime("%Y%m%d%H%M%S %z")


def export_epg(
    _session: Session, from_time: int, to_time: int, kill_event: threading.Event = None
):
    """
    Exports all EPG data between two timestamps to an XMLTV file.

    :param _session: requests.Session object
    :param from_time: Unix timestamp of the start time
    :param to_time: Unix timestamp of the end time
    :param kill_event: threading.Event object to kill the thread (optional)
    :return: None
    """
    xbmc.log(
        f"{handle} Exporting EPG data from {unix_to_epg_time(from_time)} to {unix_to_epg_time(to_time)} started",
        xbmc.LOGINFO,
    )
    dialog = xbmcgui.Dialog()
    try:
        path = get_path(is_epg=True)
    except IOError as e:
        dialog.notification(
            addon.getAddonInfo("name"),
            addon.getLocalizedString(30081),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return
    if not all([addon.getSetting("username"), addon.getSetting("password")]):
        dialog.notification(
            addon.getAddonInfo("name"),
            addon.getLocalizedString(30082),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return
    authenticate(_session)
    # channel data
    channels = media_list.get_channel_list(
        _session,
        addon.getSetting("kstoken"),
        addon.getSettingBool("listofficial"),
        api_version=addon.getSetting("apiversion"),
        client_tag=addon.getSetting("clienttag"),
    )
    channel_data = []
    program_data = []
    for channel in channels:
        # check if we need to abort
        if kill_event and kill_event.is_set():
            return
        channel_id = channel.get("id")
        if not channel_id:
            continue
        name = channel.get("name").strip()
        images = channel.get("images")
        image = None
        if images:
            image = (
                next(
                    (image for image in images if image.get("ratio") == "16x9"),
                    images[0],
                )["url"]
                + "/width/240"
            )
        # get epg data for channel
        epg_data = media_list.get_epg_by_linear_asset(
            _session,
            addon.getSetting("kstoken"),
            channel_id,
            from_time,
            to_time,
            api_version=addon.getSetting("apiversion"),
            client_tag=addon.getSetting("clienttag"),
        )
        channel = {
            "@id": channel_id,
            "display-name": name,
            "icon": {"@src": image},
        }
        channel_data.append(channel)
        for epg in epg_data:
            # check if we need to abort
            if kill_event and kill_event.is_set():
                return
            program_start_date = unix_to_epg_time(epg.get("startDate", 0))
            program_end_date = unix_to_epg_time(epg.get("endDate", 0))
            program_name = epg.get("name")
            program_description = epg.get("description")
            images = epg.get("images")
            program_image = None
            if images:
                program_image = (
                    next(
                        (image for image in images if image.get("ratio") == "16x9"),
                        images[0],
                    )["url"]
                    + "/width/240"
                )
            program_tags = epg.get("tags", {})
            program_content_type = program_tags.get("Content Type", {}).get(
                "value", "Unknown"
            )
            program_year = program_tags.get("Year", {}).get("value", "Unknown")

            program = {
                "@start": program_start_date,
                "@stop": program_end_date,
                "@channel": channel_id,
                "title": {"lang": "hu", "#text": program_name},
                "desc": {"lang": "hu", "#text": program_description},
                "icon": {"@src": program_image},
                "category": program_content_type,
                "date": program_year + "000000 +0000",
            }
            program_data.append(program)
    xmltv_data = {
        "tv": {
            "@generator-info-name": "plugin.video.notyet",
            "@generator-info-url": "",
            "channel": channel_data,
            "programme": program_data,
        }
    }
    # convert dict to XML and write to file
    with open(path, "w", encoding="utf-8") as f:
        xmltodict.unparse(xmltv_data, output=f, encoding="utf-8")
    dialog.notification(
        addon.getAddonInfo("name"),
        addon.getLocalizedString(30096),
        xbmcgui.NOTIFICATION_INFO,
    )
    addon.setSetting("lastepgupdate", str(int(time())))


class EPGUpdaterThread(threading.Thread):
    """
    A thread that updates the EPG data in the background.
    """

    def __init__(
        self,
        _session: Session,
        from_time: int,
        to_time: int,
        frequency: int,
        last_updated: int,
    ):
        super().__init__()
        self._session = _session
        self.from_time = from_time
        self.to_time = to_time
        self.frequency = frequency
        self.last_updated = last_updated
        self.killed = threading.Event()
        self.failed_count = 0

    @property
    def now(self) -> int:
        """Returns the current time in unix format"""
        return int(time())

    @property
    def from_time_from_now(self) -> int:
        """
        Returns the from_time in unix format, but relative to the current time.
        """
        return self.now - self.from_time

    @property
    def to_time_from_now(self) -> int:
        """
        Returns the to_time in unix format, but relative to the current time.
        """
        return self.now + self.to_time

    def run(self):
        """
        EPG update thread's main loop.
        """
        while not self.killed.is_set():
            xbmc.log(
                f"{handle} EPG update: next update in {min(self.frequency, self.frequency - (self.now - self.last_updated))} seconds",
                xbmc.LOGINFO,
            )
            self.killed.wait(
                min(self.frequency, self.frequency - (self.now - self.last_updated))
            )
            if not self.killed.is_set() and not self.failed_count > addon.getSettingInt(
                "epgfetchtries"
            ):
                try:
                    export_epg(
                        self._session,
                        self.from_time_from_now,
                        self.to_time_from_now,
                        self.killed,
                    )
                    self.last_updated = self.now
                    self.failed_count = 0
                except Exception as e:
                    self.failed_count += 1
                    xbmc.log(
                        f"{handle} EPG update failed: {e}",
                        xbmc.LOGERROR,
                    )
                    self.killed.wait(5)

    def stop(self):
        """
        Sets stop event to the thread.
        """
        self.killed.set()


def int_to_time(value: int) -> int:
    """Converts an integer to a time string using a lookup table"""
    options = {
        0: 3 * 60 * 60,
        1: 6 * 60 * 60,
        2: 12 * 60 * 60,
        3: 24 * 60 * 60,
        4: 48 * 60 * 60,
        5: 72 * 60 * 60,
    }
    return options.get(value, 12 * 60 * 60)


def days_to_seconds(days: int) -> int:
    """Converts days to a seconds"""
    return days * 24 * 60 * 60


def main_service():
    """
    Main service loop.
    """
    if not addon.getSettingBool("autoupdateepg"):
        xbmc.log(
            f"{handle} EPG autoupdate disabled, won't start", level=xbmc.LOGWARNING
        )
        return
    if not all([addon.getSetting("username"), addon.getSetting("password")]):
        xbmc.log(f"{handle} No credentials set, won't start", level=xbmc.LOGWARNING)
        return
    _session = Session()
    authenticate(_session)
    if not addon.getSetting("kstoken"):
        xbmc.log(f"{handle} No KSToken set, won't start", level=xbmc.LOGWARNING)
        return
    # get epg settings
    from_time = addon.getSetting("epgfrom")
    to_time = addon.getSetting("epgto")
    frequency = addon.getSetting("epgupdatefreq")
    last_update = addon.getSetting("lastepgupdate")
    if not last_update:
        last_update = 0
    else:
        last_update = int(last_update)
    if not all([from_time, to_time, frequency]):
        xbmc.log(f"{handle} EPG settings not set, won't start", level=xbmc.LOGWARNING)
        return
    from_time = days_to_seconds(int(from_time))
    to_time = days_to_seconds(int(to_time))
    frequency = int_to_time(int(frequency))
    # start epg updater thread
    monitor = xbmc.Monitor()
    epg_updater = EPGUpdaterThread(_session, from_time, to_time, frequency, last_update)
    epg_updater.start()
    xbmc.log(f"{handle} Export EPG service started", level=xbmc.LOGINFO)
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break
    epg_updater.stop()
    try:
        epg_updater.join()
    except RuntimeError:
        pass
    xbmc.log(f"{handle} Export EPG service stopped", level=xbmc.LOGINFO)


if __name__ == "__main__":
    main_service()
