import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeError(RuntimeError):
    pass


class YouTubeClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
        if not self.api_key:
            raise YouTubeError("YOUTUBE_API_KEY is not set")

    def _get(self, endpoint, params):
        query = dict(params)
        query["key"] = self.api_key
        url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                if e.code in (403, 429) and "quota" in body.lower():
                    raise YouTubeError(f"YouTube quota exceeded: {body[:300]}") from e
                last_err = YouTubeError(f"YouTube API error {e.code} on {endpoint}: {body[:300]}")
                if e.code >= 500:
                    time.sleep(1 + attempt)
                    continue
                raise last_err
            except urllib.error.URLError as e:
                last_err = YouTubeError(f"YouTube network error on {endpoint}: {e}")
                time.sleep(1 + attempt)
        raise last_err

    def search_videos(self, query, published_after, max_results=25,
                       relevance_language=None, region_code=None, order="relevance"):
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "publishedAfter": published_after,
            "maxResults": max_results,
            "safeSearch": "moderate",
        }
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        if region_code:
            params["regionCode"] = region_code
        data = self._get("search", params)
        return data.get("items", [])

    def get_videos(self, video_ids):
        items = []
        for chunk in _chunks(video_ids, 50):
            if not chunk:
                continue
            data = self._get("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(chunk)})
            items.extend(data.get("items", []))
        return items

    def get_channels(self, channel_ids):
        items = []
        for chunk in _chunks(channel_ids, 50):
            if not chunk:
                continue
            data = self._get("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)})
            items.extend(data.get("items", []))
        return items

    def get_channel_by_handle(self, handle):
        data = self._get("channels", {"part": "snippet,statistics,contentDetails",
                                       "forHandle": handle.lstrip("@")})
        items = data.get("items", [])
        return items[0] if items else None

    def get_playlist_items(self, playlist_id, max_results=15):
        data = self._get("playlistItems", {
            "part": "contentDetails,snippet",
            "playlistId": playlist_id,
            "maxResults": max_results,
        })
        return data.get("items", [])


def _chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
