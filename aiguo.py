# -*- coding: utf-8 -*-
import json
import sys
import uuid
from urllib.parse import quote

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider

BRAND_NAME = "蝴蝶影视"
BRAND_ACTOR = "🦋 TG群: @tvshare23"
BRAND_DIRECTOR = "🦋 蝴蝶影视"
TG_GROUP = "https://t.me/tvshare23"
SYNOPSIS_GROUP = "🦋 蝴蝶影视官方交流群：@tvshare23"
DIVIDER_THIN = "────────────────────"
DIVIDER_THICK = "━━━━━━━━━━━━━━"
MARKER = "〔影片简介〕"
LINE_NAME = "🦋 蝴蝶专线"
NODE_LINE = "当前节点：https://aigo.me"
HOST = "https://aigo.me"
API = "https://aigo.me/api/ui"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class Spider(BaseSpider):
    def getName(self):
        return "爱果短剧"

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Referer": HOST + "/"})
        self.classes = []
        try:
            data = self._api("/catalog/categories")
            for c in data.get("data") or []:
                self.classes.append({"type_id": c.get("id"), "type_name": c.get("name")})
        except Exception:
            pass
        if not self.classes:
            self.classes = [
                {"type_id": "2fabdc14-040d-4521-a384-01ff6739f263", "type_name": "黄果短剧"},
                {"type_id": "550d33e8-fc22-4d3e-9548-80426fa68718", "type_name": "爱果原创"},
                {"type_id": "6d650047-4b52-4099-8f32-3edac58526ee", "type_name": "魔改短剧"},
            ]

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def destroy(self):
        pass

    def _api(self, path, params=None):
        last = None
        for _ in range(3):
            try:
                r = self.session.get(API + path, params=params, timeout=30)
                if r.status_code == 200:
                    return r.json()
                last = r.status_code
            except Exception as e:
                last = e
        raise RuntimeError(str(last))

    def _remarks(self, d):
        total = d.get("episodeCount") or 0
        pub = d.get("publishedEpisodeCount") or total
        try:
            total = int(total)
            pub = int(pub)
        except Exception:
            return ""
        base = ""
        if total and pub < total:
            base = f"更新至{pub}集"
        elif total:
            base = f"全{total}集"
        if d.get("isVip"):
            base = (base + " · VIP").strip(" ·")
        return base

    def _vod(self, d):
        return {
            "vod_id": d.get("id") or "",
            "vod_name": d.get("title") or "",
            "vod_pic": d.get("coverUrl") or "",
            "vod_remarks": self._remarks(d),
        }

    def _list_result(self, data, pg):
        items = data.get("data") or []
        videos = [self._vod(d) for d in items if isinstance(d, dict)]
        return {
            "list": videos,
            "page": int(data.get("page") or pg),
            "pagecount": int(data.get("totalPages") or 1),
            "limit": int(data.get("pageSize") or 20),
            "total": int(data.get("total") or len(videos)),
        }

    def homeContent(self, filter):
        return {"class": self.classes, "filters": {}}

    def homeVideoContent(self):
        data = self._api("/catalog/dramas", {"page": 1, "pageSize": 20})
        return {"list": self._list_result(data, 1)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        data = self._api("/catalog/dramas", {"page": int(pg), "pageSize": 20, "categoryId": tid})
        return self._list_result(data, pg)

    def detailContent(self, ids):
        did = ids[0]
        detail = self._api("/catalog/dramas/" + did)
        d = detail.get("data") if isinstance(detail.get("data"), dict) else detail
        episodes = []
        page = 1
        total_pages = 1
        while page <= total_pages and page <= 20:
            ed = self._api(f"/catalog/dramas/{did}/episodes", {"page": page, "pageSize": 100})
            episodes.extend(ed.get("data") or [])
            total_pages = int(ed.get("totalPages") or 1)
            page += 1
        parts = []
        for ep in episodes:
            num = ep.get("episodeNumber")
            epid = ep.get("id")
            if num is None or not epid:
                continue
            name = ep.get("title") or ""
            if not name or str(name).strip() in (str(num), f"第{num}集"):
                name = f"第{num}集"
            if ep.get("isVip"):
                name = name + " · VIP"
            parts.append(f"{name}${did}|{epid}|{num}")
        tags = []
        for t in d.get("tags") or []:
            if isinstance(t, dict) and t.get("name"):
                tags.append(t["name"])
        year = ""
        upd = d.get("lastContentPublishedAt") or d.get("updatedAt") or ""
        if isinstance(upd, str) and len(upd) >= 4:
            year = upd[:4]
        intro = d.get("description") or ""
        content = "\n".join([
            DIVIDER_THICK,
            f"🦋 品牌：{BRAND_NAME}",
            NODE_LINE,
            f"📡 线路：{LINE_NAME}",
            f"👥 交流群：{SYNOPSIS_GROUP}",
            DIVIDER_THIN,
            MARKER,
            intro,
        ])
        vod = {
            "vod_id": did,
            "vod_name": d.get("title") or "",
            "vod_pic": d.get("coverUrl") or "",
            "vod_year": year,
            "vod_area": "",
            "vod_remarks": self._remarks(d),
            "vod_actor": BRAND_ACTOR,
            "vod_director": BRAND_DIRECTOR,
            "vod_content": content,
            "type_name": " / ".join([x for x in [d.get("category") or ""] + tags if x]),
            "vod_play_from": LINE_NAME,
            "vod_play_url": "#".join(parts),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = self._api("/catalog/dramas", {"page": int(pg), "pageSize": 20, "q": key})
        return self._list_result(data, pg)

    def playerContent(self, flag, id, vipFlags):
        parts = id.split("|")
        epid = parts[1] if len(parts) > 1 else parts[0]
        header = {"User-Agent": UA, "Referer": HOST + "/"}
        url = ""
        key = str(uuid.uuid4())
        for attempt in range(2):
            try:
                r = self.session.post(
                    API + "/episodes/" + epid + "/playback",
                    data="{}",
                    headers={"Content-Type": "application/json", "Idempotency-Key": key},
                    timeout=30,
                )
                if r.status_code == 200:
                    url = (r.json() or {}).get("playUrl") or ""
                    break
                if r.status_code == 401:
                    try:
                        code = (r.json() or {}).get("code") or ""
                    except Exception:
                        code = ""
                    if code == "PLAYBACK_GUEST_COOKIE_REQUIRED" and attempt == 0:
                        continue
                break
            except Exception:
                break
        if url:
            return {"parse": 0, "playUrl": "", "url": url, "header": header}
        drama = parts[0]
        num = parts[2] if len(parts) > 2 else "1"
        web = f"{HOST}/play/{drama}?ep={num}&episodeId={epid}"
        return {"parse": 1, "playUrl": "", "url": web, "header": header}

    def localProxy(self, param):
        return None

    def liveContent(self, url):
        return {"list": []}

    def manualVideoCheck(self):
        return False
