import threading
from sys import argv
from urllib.parse import parse_qsl

import requests
import xbmc
import xbmcaddon
from export_data import main_service
from resources.lib.yeti import static

# script responsible for monitoring playback and
# doing keepalive requests if the playback is from plugin.video.notyet
# and the media playback is paused
# once the playback is stopped, also sends a teardown request

handle = "[NotYet]"
timeout = 5
addon = xbmcaddon.Addon()

xbmc.log(f"{handle} Playback Manager Service started", xbmc.LOGINFO)


def report_playback(
    params: dict, user_agent: str, playing_state: str, position: float
) -> None:
    """
    Sends playback status to the Yeti API

    :param params: The parameters of the playback
    :param user_agent: The user agent to use
    :param playing_state: The state of the playback (ie. HIT, PLAY, STOP, etc.)
    :param position: The position of the playback
    """
    data = {
        "apiVersion": addon.getSetting("drmapiversion") or static.drm_api_version,
        "bookmark": {
            "objectType": f"{static.get_ott_platform_name()}Bookmark",
            "type": params.get("type"),
            "context": params.get("context"),
            "id": int(params.get("id")),
            "position": position,
            "playerData": {
                "objectType": f"{static.get_ott_platform_name()}BookmarkPlayerData",
                "action": playing_state,
                "averageBitrate": 0,
                "totalBitrate": 0,
                "currentBitrate": 0,
                "fileId": int(params.get("fileId")),
            },
            "programId": params.get("programId"),
        },
        "ks": addon.getSetting("kstoken"),
    }
    xbmc.log(
        f"{handle} Playback Manager Service: sending bookmark request: {playing_state}",
        xbmc.LOGDEBUG,
    )
    try:
        response = requests.post(
            f"{static.get_ott_base()}api_v3/service/bookmark/action/add",
            json=data,
            headers={"User-Agent": user_agent},
            timeout=3,
        )
        xbmc.log(
            f"{handle} Playback Manager Service: bookmark request data: {str(data).replace(addon.getSetting('kstoken'), '***')}",
            xbmc.LOGDEBUG,
        )
        xbmc.log(
            f"{handle} Playback Manager Service: bookmark request response: [{response.status_code}] {response.text}",
            xbmc.LOGDEBUG,
        )
    except requests.exceptions.RequestException as e:
        xbmc.log(
            f"{handle} Playback Manager Service: bookmark request error: {e}",
            xbmc.LOGERROR,
        )


class KeepaliveThread(threading.Thread):
    def __init__(self, played_url, user_agent):
        threading.Thread.__init__(self)
        self.played_url = played_url
        self.user_agent = user_agent
        self.keepalive_killed = threading.Event()

    def run(self):
        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent})
        url = self.played_url.replace("?bkm-query", "/keepalive")
        while not self.keepalive_killed.is_set():
            self.keepalive_killed.wait(timeout=timeout)
            if not self.keepalive_killed.is_set():
                try:
                    response = session.get(url, timeout=timeout)
                    xbmc.log(
                        f"{handle} Playback Manager Service: keepalive request response: {response.status_code}",
                        xbmc.LOGDEBUG,
                    )
                except requests.exceptions.RequestException as e:
                    xbmc.log(
                        f"{handle} Playback Manager Service: keepalive request error: {e}",
                        xbmc.LOGERROR,
                    )

    def stop(self):
        self.keepalive_killed.set()


class PlaybackStatReporterThread(threading.Thread):
    def __init__(self, user_agent, report_params):
        threading.Thread.__init__(self)
        self.user_agent = user_agent
        self.report_params = report_params
        self.player = xbmc.Player()
        self.report_killed = threading.Event()
        self.last_position = 0

    def run(self):
        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent})
        while not self.report_killed.is_set():
            self.report_killed.wait(timeout=30)
            if not self.report_killed.is_set() and self.player.isPlayingVideo():
                self.last_position = self.player.getTime()
                report_playback(
                    self.report_params, self.user_agent, "HIT", self.last_position
                )

    def stop(self):
        self.report_killed.set()


class XBMCPlayer(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        self.user_agent = addon.getSetting("useragent")
        self.played_url = ""
        self.report_params = {}
        self.keepalive_thread = None
        self.report_thread = None
        self.reporting = addon.getSettingBool("reportingon")

    def onPlayBackStarted(self):
        # we need the playback stop when the user switches to another video
        # and doesn't stop inbetween, so we can send a teardown request
        self.onPlayBackStopped()
        timeout_counter = 0
        while not self.isPlayingVideo() and timeout_counter < 10:
            timeout_counter += 1
            xbmc.sleep(1000)
        if self.isPlayingVideo() and self.getVideoInfoTag().getTrailer().startswith(
            "plugin://plugin.video.notyet/"
        ):
            self.played_url = self.getPlayingFile()
            xbmc.log(
                f"{handle} Playback Manager Service: started playing {self.played_url}",
                xbmc.LOGINFO,
            )
            try:
                query = self.getVideoInfoTag().getTrailer().split("?", 1)[1]
                if self.reporting:
                    self.report_params = dict(parse_qsl(query, keep_blank_values=True))
                    report_playback(
                        self.report_params, self.user_agent, "PLAY", self.getTime()
                    )
                    if self.report_thread and self.report_thread.is_alive():
                        self.stop_report_thread()
                    self.report_thread = PlaybackStatReporterThread(
                        self.user_agent, self.report_params
                    )
                    self.report_thread.start()
                else:
                    self.report_params = None
                    xbmc.log(
                        f"{handle} Playback Manager Service: not reporting playback (disabled in settings)",
                        xbmc.LOGINFO,
                    )
            except IndexError:
                xbmc.log(
                    f"{handle} Playback Manager Service: failed to parse query string",
                    xbmc.LOGERROR,
                )
            if addon.getSettingBool("preferhundub"):
                audios = self.getAvailableAudioStreams()
                if audios:
                    audio = next((audio for audio in audios if "hu" in audio.lower()), None)
                    if audio:
                        # the sleep is required so the playback doesn't start from the beginning
                        # possibly a kodi bug
                        xbmc.sleep(3000)
                        xbmc.log(
                            f"{handle} Playback Manager Service: switching to {audio} audio",
                            xbmc.LOGINFO,
                        )
                        player.setAudioStream(audios.index(audio))

    def onPlayBackStopped(self) -> None:
        if self.played_url:
            if self.played_url.endswith("?bkm-query"):
                # replace ?bkm-query with /teardown
                url = self.played_url.replace("?bkm-query", "/teardown/200")
                xbmc.log(
                    f"{handle} Playback Manager Service: sending teardown request to {url}",
                    xbmc.LOGINFO,
                )
                response = requests.get(
                    url, timeout=timeout, headers={"User-Agent": self.user_agent}
                )
                xbmc.log(
                    f"{handle} Playback Manager Service: teardown request response: {response.status_code}",
                    xbmc.LOGDEBUG,
                )
            self.played_url = ""
        last_position = 0
        if self.report_thread and self.report_thread.is_alive():
            last_position = self.report_thread.last_position
            self.stop_report_thread()
            xbmc.log(
                f"{handle} Playback Manager Service: stopped reporting thread",
                xbmc.LOGINFO,
            )
        if self.report_params:
            report_playback(self.report_params, self.user_agent, "STOP", last_position)
            self.report_params = {}

    def onPlayBackError(self) -> None:
        return self.onPlayBackStopped()

    def onPlayBackEnded(self) -> None:
        return self.onPlayBackStopped()

    def stop_keepalive_thread(self):
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            self.keepalive_thread.stop()
            try:
                self.keepalive_thread.join()
            except RuntimeError:
                pass
        self.keepalive_thread = None

    def stop_report_thread(self):
        if self.report_thread and self.report_thread.is_alive():
            self.report_thread.stop()
            try:
                self.report_thread.join()
            except RuntimeError:
                pass
        self.report_thread = None

    def onPlayBackPaused(self) -> None:
        if not self.played_url:
            return
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            self.stop_keepalive_thread()
            xbmc.log(
                f"{handle} Playback Manager Service: stopped keepalive thread",
                xbmc.LOGINFO,
            )
        if self.report_thread and self.report_thread.is_alive():
            self.stop_report_thread()
            xbmc.log(
                f"{handle} Playback Manager Service: stopped reporting thread",
                xbmc.LOGINFO,
            )
        self.keepalive_thread = KeepaliveThread(self.played_url, self.user_agent)
        self.keepalive_thread.start()
        xbmc.log(
            f"{handle} Playback Manager Service: started keepalive thread",
            xbmc.LOGINFO,
        )
        if self.report_params:
            report_playback(
                self.report_params, self.user_agent, "PAUSE", self.getTime()
            )

    def onPlayBackResumed(self) -> None:
        if not self.played_url:
            return
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            self.stop_keepalive_thread()
            xbmc.log(
                f"{handle} Playback Manager Service: stopped keepalive thread",
                xbmc.LOGINFO,
            )
        if self.report_thread and self.report_thread.is_alive():
            self.stop_report_thread()
            xbmc.log(
                f"{handle} Playback Manager Service: stopped reporting thread",
                xbmc.LOGINFO,
            )
        if self.report_params:
            report_playback(self.report_params, self.user_agent, "PLAY", self.getTime())
            self.report_thread = PlaybackStatReporterThread(
                self.user_agent, self.report_params
            )
            self.report_thread.start()
            xbmc.log(
                f"{handle} Playback Manager Service: started reporting thread",
                xbmc.LOGINFO,
            )


if __name__ == "__main__":
    monitor = xbmc.Monitor()
    player = XBMCPlayer()
    main_service()
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break
    player.stop_keepalive_thread()
    xbmc.log(f"{handle} Playback Manager Service stopped", xbmc.LOGINFO)
