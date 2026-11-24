# -*- coding: utf-8 -*-
"""
HStream · BieCuiLe Python Spider
版本：1.5.0
适配：BieCuiLe 1.1.5（TVBox 风格 Python Spider）
站点：https://hstream.moe

功能：
- Browse 四组标签筛选 / 官网排序 / 搜索 / 分页
- 详情封面、简介、剧集列表
- CSRF 会话播放接口
- 按官网播放 API 探测 DASH 画质与 CDN，线路名称与实际地址严格对应
- MP4 备用线路经过 Range 请求验证后才展示
- 修复集数名称识别与线路选择回退错误
- 请求会话复用、超时控制、基础缓存、错误提示

分类说明：Browse 的 Actions、Genres、Types、Appearance 标签按截图录入；筛选请求使用官网 tags[index] 参数。\n依赖：requests
说明：仅访问站点公开页面及当前会话有权访问的内容；需要登录的内容请在站点正常登录后自行配置 Cookie。
"""

import json
import re
import time
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlencode

try:
    import requests
    from requests.adapters import HTTPAdapter
except Exception:
    requests = None
    HTTPAdapter = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


SITE_NAME = "HStream"
SITE_URL = "https://hstream.moe"
PAGE_SIZE = 24
UA = ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")
ORDERS = [
    ("最新上传", "recently-uploaded"),
    ("最新发行", "recently-released"),
    ("最早上传", "oldest-uploads"),
    ("最早发行", "oldest-releases"),
    ("最多播放", "view-count"),
    ("名称 A-Z", "az"),
    ("名称 Z-A", "za"),
]
TAG_GROUPS = {'actions': ('Actions', [('Anal', 'anal'), ('BDSM', 'bdsm'), ('Facial', 'facial'), ('Blow Job', 'blow-job'), ('Boob Job', 'boob-job'), ('Foot Job', 'foot-job'), ('Hand Job', 'hand-job'), ('Rimjob', 'rimjob'), ('Inflation', 'inflation'), ('Masturbation', 'masturbation'), ('Public Sex', 'public-sex'), ('Rape', 'rape'), ('Reverse Rape', 'reverse-rape'), ('Threesome', 'threesome'), ('Orgy', 'orgy'), ('Gangbang', 'gangbang')]), 'genres': ('Genres', [('Ahegao', 'ahegao'), ('Bestiality', 'bestiality'), ('Bondage', 'bondage'), ('Creampie', 'creampie'), ('Gore', 'gore'), ('Harem', 'harem'), ('Incest', 'incest'), ('Lactation', 'lactation'), ('LQ', 'lq'), ('Mind Break', 'mind-break'), ('Mind Control', 'mind-control'), ('Orc', 'orc'), ('Scat', 'scat'), ('Tentacle', 'tentacle'), ('Toys', 'toys'), ('Tsundere', 'tsundere'), ('Virgin', 'virgin'), ('Yuri', 'yuri'), ('Ugly Bastard', 'ugly-bastard'), ('Monster', 'monster')]), 'types': ('Types', [('3D', '3d'), ('4K', '4k'), ('48Fps', '48fps'), ('4K 48Fps', '4k-48fps'), ('Censored', 'censored'), ('Uncensored', 'uncensored'), ('Comedy', 'comedy'), ('Fantasy', 'fantasy'), ('Horror', 'horror'), ('Vanilla', 'vanilla'), ('Ntr', 'ntr'), ('Pov', 'pov'), ('Filmed', 'filmed'), ('X-Ray', 'x-ray')]), 'appearance': ('Appearance', [('Loli', 'loli'), ('Shota', 'shota'), ('Milf', 'milf'), ('Futanari', 'futanari'), ('Big Boobs', 'big-boobs'), ('Small Boobs', 'small-boobs'), ('Dark Skin', 'dark-skin'), ('Cosplay', 'cosplay'), ('Elf', 'elf'), ('Maid', 'maid'), ('Nekomimi', 'nekomimi'), ('Nurse', 'nurse'), ('School Girl', 'school-girl'), ('Succubus', 'succubus'), ('Teacher', 'teacher'), ('Trap', 'trap'), ('Pregnant', 'pregnant'), ('Glasses', 'glasses'), ('Swim Suit', 'swim-suit')])}
QUALITY = [("2160", "4K"), ("2160i", "4K 48fps"),
           ("1080", "1080p"), ("1080i", "1080p 48fps"),
           ("720", "720p")]


def _clean(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _origin(url):
    p = urlsplit(url)
    return "%s://%s" % (p.scheme, p.netloc)


def _valid_content_path(value):
    value = str(value or "").strip()
    p = urlsplit(value)
    path = p.path if p.scheme else value.split("?", 1)[0].split("#", 1)[0]
    return bool(re.match(r"^/hentai/[a-z0-9]+(?:-[a-z0-9]+)*$", path, re.I))


def _content_path(value, base=SITE_URL):
    url = urljoin(base.rstrip("/") + "/", str(value or ""))
    if _origin(url) != _origin(base) or not _valid_content_path(url):
        return ""
    return urlsplit(url).path.rstrip("/")


def _series_key(path):
    return re.sub(r"-\d+$", "", str(path or ""))


class _Node:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.text = []

    def attr(self, name):
        return self.attrs.get(name, "")

    def all_text(self):
        parts = list(self.text)
        for child in self.children:
            parts.append(child.all_text())
        return " ".join(x for x in parts if x)


class _HTMLTree(HTMLParser):
    VOID = set(("area", "base", "br", "col", "embed", "hr", "img", "input",
                "link", "meta", "param", "source", "track", "wbr"))

    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", [])
        self.stack = [self.root]
        try:
            self.feed(raw or "")
            self.close()
        except Exception:
            pass

    def handle_starttag(self, tag, attrs):
        node = _Node(tag.lower(), attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag.lower(), attrs))

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data and data.strip():
            self.stack[-1].text.append(data.strip())

    def walk(self, node=None):
        node = node or self.root
        for child in node.children:
            yield child
            for sub in self.walk(child):
                yield sub

    def find_all(self, tag=None):
        return [n for n in self.walk() if tag is None or n.tag == tag]


def _walk_node(node):
    yield node
    for child in node.children:
        for sub in _walk_node(child):
            yield sub


class Spider(BaseSpider):
    def __init__(self):
        self.site = SITE_URL
        self.cookie = ""
        self.timeout = 15
        self.quality = "1080"
        self.session = None
        self._cache = {}
        self._cache_ttl = 90

    def getName(self):
        return SITE_NAME

    def getDependence(self):
        return []

    def init(self, extend=""):
        # 可选扩展配置：JSON，例如 {"site":"https://hstream.moe","cookie":"","quality":"1080"}
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip().startswith("{") else {}
            self.site = str(cfg.get("site") or SITE_URL).rstrip("/")
            self.cookie = str(cfg.get("cookie") or "")
            self.quality = str(cfg.get("quality") or "1080")
            self.timeout = max(5, min(30, int(cfg.get("timeout") or 15)))
        except Exception:
            self.site = SITE_URL
        self._ensure_session()

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None

    def _ensure_session(self):
        if self.session is not None:
            return
        if requests is None:
            raise RuntimeError("当前运行环境缺少 requests 模块")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Connection": "keep-alive",
        })
        if HTTPAdapter:
            adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=1)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)

    def _headers(self, referer=None, json_mode=False):
        h = {"Referer": referer or self.site + "/"}
        if json_mode:
            h.update({"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                      "Content-Type": "application/json", "Origin": _origin(self.site)})
        if self.cookie:
            h["Cookie"] = self.cookie.strip()
        return h

    def _get(self, url, params=None, referer=None, allow_redirects=True):
        self._ensure_session()
        r = self.session.get(url, params=params, headers=self._headers(referer),
                             timeout=(5, self.timeout), allow_redirects=allow_redirects)
        if _origin(r.url) != _origin(url):
            raise RuntimeError("网页跳转到了其他站点，可能需要完成网站验证")
        if r.status_code in (401, 403, 419):
            raise RuntimeError("网站拒绝访问（%s），请检查网络、验证或登录状态" % r.status_code)
        if r.status_code == 429:
            raise RuntimeError("请求过于频繁，请稍后再试")
        r.raise_for_status()
        if not r.text.strip():
            raise RuntimeError("网站返回空页面")
        if "challenge-running" in r.text or "Just a moment" in r.text:
            raise RuntimeError("网站要求浏览器验证，当前请求无法通过验证")
        return r

    def _post_json(self, url, data, referer, csrf=""):
        self._ensure_session()
        headers = self._headers(referer, True)
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        else:
            match = re.search(r"(?:^|;\s*)XSRF-TOKEN=([^;]+)", self.cookie, re.I)
            if match:
                from urllib.parse import unquote
                headers["X-XSRF-TOKEN"] = unquote(match.group(1))
        r = self.session.post(url, json=data, headers=headers,
                              timeout=(5, self.timeout))
        if r.status_code in (401, 403, 419):
            raise RuntimeError("播放接口拒绝访问或会话已过期，请刷新页面/登录")
        if r.status_code == 429:
            raise RuntimeError("播放接口请求过于频繁")
        r.raise_for_status()
        try:
            obj = r.json()
        except Exception:
            raise RuntimeError("播放接口没有返回有效 JSON")
        if not isinstance(obj, dict):
            raise RuntimeError("播放接口数据结构无效")
        return obj

    def _page(self, page, order, keyword="", tags=None):
        params = {"order": order, "page": str(page)}
        if keyword:
            params["search"] = keyword
        for index, tag in enumerate(tags or []):
            params["tags[%d]" % index] = tag
        url = self.site + "/search"
        return self._get(url, params=params).text

    @staticmethod
    def _has_class(node, word):
        return word.lower() in (node.attr("class") or "").lower().split()

    def _parse_cards(self, raw, page=1):
        # Selector/title priority ported from the supplied official WeBox source.
        tree = _HTMLTree(raw)
        items, seen = [], set()
        for a in tree.find_all("a"):
            path = _content_path(a.attr("href"), self.site)
            if not path or path in seen:
                continue
            nodes = list(_walk_node(a))
            img = next((n for n in nodes if n.tag == "img"), None)
            title_node = next((n for n in nodes
                               if n.tag in ("h2", "h3", "h4") or
                               "title" in (n.attr("class") or "").split()), None)
            title = _clean(title_node.all_text() if title_node else "")
            if not title and img:
                title = _clean(img.attr("alt"))
            if not title:
                title = _clean(a.attr("title"))
            if not title or (img is None and title_node is None):
                continue
            poster = ""
            if img:
                poster = (img.attr("data-src") or img.attr("data-lazy-src") or
                          img.attr("data-original") or img.attr("src"))
                if not poster:
                    srcset = img.attr("srcset") or img.attr("data-srcset")
                    if srcset:
                        poster = srcset.split(",")[0].strip().split(" ")[0]
                if poster:
                    poster = urljoin(self.site + "/", poster)
            item = self._vod_item(path, title, poster)
            item["vod_remarks"] = "剧集" if re.search(r"-\d+$", path) else "HStream"
            items.append(item)
            seen.add(path)
        return items, self._has_next(tree, page)

    def _has_next(self, tree, page=1):
        for n in tree.find_all():
            if n.tag not in ("a", "button"):
                continue
            if n.attr("disabled") or n.attr("aria-disabled") == "true":
                continue
            if self._has_class(n, "disabled"):
                continue
            wire = n.attr("wire:click") or ""
            if re.match(r"^nextPage(?:\(|$)", wire):
                return True
            if n.attr("rel") == "next":
                m = re.search(r"[?&]page=(\d+)(?:&|$)", n.attr("href") or "")
                if m and int(m.group(1)) > int(page):
                    return True
        return False

    def _vod_item(self, path, title, poster="", summary=""):
        return {
            "vod_id": path,
            "vod_name": _clean(title)[:240],
            "vod_pic": poster,
            "vod_remarks": "HStream · HD",
            "vod_content": _clean(summary)[:2000],
        }

    def _cached_browse(self, page, order, keyword="", tags=None):
        tags = tuple(tags or [])
        key = (page, order, keyword, tags)
        now = time.time()
        old = self._cache.get(key)
        if old and now - old[0] < self._cache_ttl:
            return old[1]
        raw = self._page(page, order, keyword, tags)
        items, has_next = self._parse_cards(raw, page)
        result = {"list": items, "page": page, "pagecount": page + (1 if has_next else 0),
                  "limit": PAGE_SIZE, "total": 999999}
        self._cache[key] = (now, result)
        return result

    def homeContent(self, filter):
        filters = [{
            "key": "order", "name": "排序方式",
            "value": [{"n": label, "v": value} for label, value in ORDERS],
        }]
        for key, (label, options) in TAG_GROUPS.items():
            filters.append({
                "key": key, "name": label,
                "value": [{"n": name, "v": slug} for name, slug in options],
            })
        return {
            "class": [{"type_id": "browse", "type_name": "Browse"}],
            "filters": {"browse": filters},
        }

    def homeVideoContent(self):
        try:
            return {"list": self._cached_browse(1, "recently-uploaded")["list"]}
        except Exception:
            return {"list": []}

    def _read_extend(self, extend):
        if isinstance(extend, str) and extend.strip():
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        return extend if isinstance(extend, dict) else {}

    def _selected_tags(self, extend):
        selected = []
        for key, (_, options) in TAG_GROUPS.items():
            value = extend.get(key)
            if isinstance(value, (list, tuple)):
                values = value
            else:
                values = [value]
            valid = {slug for _, slug in options}
            for item in values:
                item = str(item or "").strip().lower()
                if item in valid and item not in selected:
                    selected.append(item)
        # Also accept an explicit tags array for clients that support multi-select.
        extra = extend.get("tags", [])
        if isinstance(extra, str):
            extra = [x.strip() for x in extra.split(",")]
        if isinstance(extra, (list, tuple)):
            all_slugs = {slug for _, options in TAG_GROUPS.values() for _, slug in options}
            for item in extra:
                item = str(item or "").strip().lower()
                if item in all_slugs and item not in selected:
                    selected.append(item)
        return selected[:32]

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        ext = self._read_extend(extend)
        order = ext.get("order") or "recently-uploaded"
        if tid in [x[1] for x in ORDERS]:
            order = tid
        if order not in [x[1] for x in ORDERS]:
            order = "recently-uploaded"
        tags = self._selected_tags(ext)
        return self._cached_browse(page, order, tags=tags)

    def searchContent(self, key, quick, pg="1"):
        page = max(1, int(pg or 1))
        keyword = re.sub(r"\s+", " ", str(key or "")).strip()
        if not keyword:
            return {"list": [], "page": page, "pagecount": 0, "limit": PAGE_SIZE, "total": 0}
        return self._cached_browse(page, "recently-uploaded", keyword)

    def _detail_page(self, path):
        path = _content_path(path, self.site)
        if not path:
            raise RuntimeError("内容地址无效，请重新打开详情")
        r = self._get(urljoin(self.site + "/", path.lstrip("/")))
        return path, r.url, r.text

    def _extract_title(self, tree):
        for n in tree.find_all("h1"):
            title = _clean(n.all_text())
            if title:
                return title
        for n in tree.find_all("meta"):
            if n.attr("property") == "og:title":
                return _clean(n.attr("content"))
        for n in tree.find_all("title"):
            value = _clean(n.all_text())
            if value:
                return re.sub(r"\s*\|\s*hstream\.moe.*$", "", value, flags=re.I).strip()
        return SITE_NAME

    def _extract_poster(self, tree, base):
        for n in tree.find_all("meta"):
            if n.attr("property") == "og:image" and n.attr("content"):
                return urljoin(base, n.attr("content"))
        for n in tree.find_all("img"):
            marker = (n.attr("alt") + " " + n.attr("src") + " " +
                      n.attr("data-src") + " " + n.attr("class")).lower()
            if "cover" in marker:
                raw = (n.attr("data-src") or n.attr("data-lazy-src") or
                       n.attr("data-original") or n.attr("src"))
                if raw:
                    return urljoin(base, raw)
        return ""

    def _extract_summary(self, tree):
        # Official WeBox logic: Description/Synopsis heading's next sibling,
        # then og:description / meta description fallback.
        for parent in [tree.root] + list(tree.walk()):
            for index, node in enumerate(parent.children):
                if node.tag not in ("h2", "h3", "h4"):
                    continue
                if _clean(node.all_text()).lower() not in ("description", "synopsis", "简介"):
                    continue
                if index + 1 < len(parent.children):
                    value = _clean(parent.children[index + 1].all_text())
                    if value:
                        return value
        for n in tree.find_all("meta"):
            if n.attr("property") == "og:description" or n.attr("name") == "description":
                value = _clean(n.attr("content"))
                if value and not value.lower().startswith("stream english subbed"):
                    return value
        return ""

    def _episode_paths(self, tree, content_path, raw):
        prefix = _series_key(content_path)
        found = set()
        for n in tree.find_all("a"):
            p = _content_path(n.attr("href"), self.site)
            if p and _series_key(p) == prefix and re.search(r"-\d+$", p):
                found.add(p)
        if re.search(r"-\d+$", content_path) or re.search(r"""["\'](?:episode_id|e_id)["\']\s*:""", raw):
            found.add(content_path)
        if not found:
            found.add(content_path)
        return sorted(found, key=lambda x: int(re.search(r"-(\d+)$", x).group(1)) if re.search(r"-(\d+)$", x) else 0)

    def detailContent(self, ids):
        path = ids[0] if isinstance(ids, (list, tuple)) else str(ids).split(",")[0]
        content_path, final_url, raw = self._detail_page(path)
        tree = _HTMLTree(raw)
        title = self._extract_title(tree)
        poster = self._extract_poster(tree, final_url)
        summary = self._extract_summary(tree)
        episodes = self._episode_paths(tree, content_path, raw)
        episode_names = [
            ("第 %s 集" % re.search(r"-(\d+)$", ep).group(1) if re.search(r"-(\d+)$", ep) else "正片", ep)
            for i, ep in enumerate(episodes, 1)
        ]

        # Discover playable routes using the same API/manifest flow as the official WeBox source.
        try:
            discovered = self._play_sources(episodes[0])
        except Exception:
            discovered = []

        route_names = []
        for source in discovered:
            if source[0] not in route_names:
                route_names.append(source[0])
        if not route_names:
            route_names = ["HStream 自动线路"]

        route_urls = []
        for route_name in route_names:
            route_urls.append("#".join(
                episode_name + "$" + episode_path
                for episode_name, episode_path in episode_names
            ))

        vod = self._vod_item(content_path, title, poster, summary)
        vod.update({
            "vod_play_from": "$$$".join(route_names),
            "vod_play_url": "$$$".join(route_urls),
            "vod_content": summary or "HStream 在线视频",
        })
        return {"list": [vod]}

    def _csrf(self, tree):
        for n in tree.find_all("meta"):
            if n.attr("name") == "csrf-token":
                return n.attr("content")
        for n in tree.find_all("input"):
            if n.attr("name") == "_token":
                return n.attr("value")
        return ""

    def _episode_id(self, tree, raw):
        for n in tree.find_all("input"):
            if n.attr("id") == "e_id" or n.attr("name") == "episode_id":
                value = n.attr("value")
                if value.isdigit():
                    return value
        m = re.search(r'["\'](?:episode_id|e_id)["\']\s*:\s*["\']?(\d+)', raw)
        return m.group(1) if m else ""

    def _stream_domains(self, payload):
        primary = payload.get("stream_domains") or payload.get("stream_domain") or []
        fallback = payload.get("asia_stream_domains") or []
        if not isinstance(primary, list):
            primary = [primary]
        if not isinstance(fallback, list):
            fallback = [fallback]
        values = (primary[:1] + fallback + primary[1:])[:3]
        result = []
        for x in values:
            if not isinstance(x, str) or not x.startswith(("http://", "https://")):
                continue
            u = x.rstrip("/")
            if u not in result and not urlsplit(u).query and not urlsplit(u).fragment:
                result.append(u)
        return result

    def _verify_mp4(self, url, headers):
        """Verify the MP4 endpoint with a tiny range request, not just a guessed URL."""
        try:
            response = self.session.get(
                url, headers=dict(headers, Range="bytes=0-1"),
                timeout=(4, 8), stream=True, allow_redirects=True
            )
            try:
                if response.status_code not in (200, 206):
                    return False
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "text/html" in content_type or "json" in content_type:
                    return False
                sample = next(response.iter_content(2), b"")
                return bool(sample) and ("video/" in content_type or
                    "octet-stream" in content_type or response.status_code == 206)
            finally:
                response.close()
        except Exception:
            return False

    def _play_sources(self, episode_path):
        """Extract playable entries from the official player API and verify DASH manifests."""
        path, episode_url, raw = self._detail_page(episode_path)
        tree = _HTMLTree(raw)
        eid = self._episode_id(tree, raw)

        direct = []
        seen_direct = set()
        for node in tree.find_all():
            candidate = node.attr("href") or node.attr("src")
            if not candidate:
                continue
            media_url = urljoin(episode_url, candidate)
            if not re.search(r"\.mp4(?:$|[?#])", media_url, re.I):
                continue
            if media_url not in seen_direct:
                seen_direct.add(media_url)
                direct.append(media_url)

        sources = []
        payload = None
        api_error = None
        if eid:
            csrf = self._csrf(tree)
            if not csrf and self.cookie:
                match = re.search(r"(?:^|;\s*)XSRF-TOKEN=([^;]+)", self.cookie, re.I)
                if match:
                    from urllib.parse import unquote
                    csrf = unquote(match.group(1))
            if csrf:
                try:
                    payload = self._post_json(
                        urljoin(self.site + "/", "/player/api"),
                        {"episode_id": eid}, episode_url, csrf=csrf
                    )
                except Exception as exc:
                    api_error = exc
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    payload = payload["data"]

        if isinstance(payload, dict) and payload.get("stream_url"):
            stream_path = str(payload.get("stream_url") or "").strip("/")
            parts = stream_path.split("/")
            safe_path = (
                bool(stream_path) and len(stream_path) <= 4096
                and not re.search(r"[?#\\\r\n]", stream_path)
                and all(part and part not in (".", "..") and
                        not re.search(r"%2e|%2f|%5c", part, re.I)
                        for part in parts)
            )
            if safe_path:
                domains = self._stream_domains(payload)
                codes = ["720", "1080", "2160"]
                if int(payload.get("interpolated") or 0) == 1:
                    codes.append("1080i")
                if int(payload.get("interpolated_uhd") or 0) == 1:
                    codes.append("2160i")
                codes.sort(key=lambda code: 0 if code == self.quality else 1)

                headers = {
                    "User-Agent": UA,
                    "Referer": episode_url,
                    "Origin": _origin(episode_url),
                }

                # Check CDN domains in official priority order; verify every quality in parallel.
                for domain in domains[:3]:
                    candidates = {}
                    with ThreadPoolExecutor(max_workers=max(1, min(5, len(codes)))) as pool:
                        pending = {}
                        for code in codes:
                            manifest = domain + "/" + stream_path + "/" + code + "/manifest.mpd"
                            future = pool.submit(
                                self.session.get, manifest,
                                headers=headers, timeout=(4, 8)
                            )
                            pending[future] = (code, manifest)
                        for future in as_completed(pending):
                            code, manifest = pending[future]
                            try:
                                response = future.result()
                                body = response.text or ""
                                valid_mpd = (
                                    response.ok
                                    and re.search(r"<(?:[\w.-]+:)?MPD(?:\s|>)", body, re.I)
                                    and re.search(r"<(?:[\w.-]+:)?Period(?:\s|>)", body, re.I)
                                    and re.search(r"<(?:[\w.-]+:)?Representation(?:\s|>)", body, re.I)
                                )
                                protected = re.search(
                                    r"<(?:[\w.-]+:)?ContentProtection(?:\s|>)", body, re.I
                                )
                                if valid_mpd and not protected:
                                    candidates[code] = manifest
                            except Exception:
                                continue

                    for code in codes:
                        if code in candidates:
                            sources.append((
                                dict(QUALITY).get(code, code) + " [DASH]",
                                candidates[code], headers
                            ))
                    if sources:
                        break

                # The official player exposes a 720p MP4 fallback. Only publish it
                # after a real byte-range request succeeds; a guessed URL is not a route.
                if domains:
                    mp4 = domains[0] + "/" + stream_path + "/x264.720p.mp4"
                    if self._verify_mp4(mp4, headers):
                        sources.append(("720p MP4 备用", mp4, headers))

        for media_url in direct:
            direct_headers = {"User-Agent": UA, "Referer": episode_url,
                              "Origin": _origin(episode_url)}
            if (not any(item[1] == media_url for item in sources)
                    and self._verify_mp4(media_url, direct_headers)):
                sources.append(("MP4 直链", media_url, direct_headers))

        if not sources:
            if api_error:
                raise RuntimeError("播放接口请求失败：%s" % api_error)
            raise RuntimeError("没有找到可用播放线路；请检查登录状态、Cookie 或站点验证")
        return sources

    def playerContent(self, flag, id, vipFlags):
        episode_path = str(id or "").split("$", 1)[-1]
        sources = self._play_sources(episode_path)

        # The selected vod_play_from entry must resolve to that exact route.
        # Never silently play a different quality/CDN when a route is missing.
        selected_flag = str(flag or "").strip()
        chosen = next((item for item in sources if item[0] == selected_flag), None)
        if chosen is None:
            if selected_flag in ("HStream 高清", "HStream 自动线路", ""):
                chosen = next((item for item in sources if "[DASH]" in item[0]),
                              sources[0] if sources else None)
            if chosen is None:
                raise RuntimeError("所选线路当前不可用：%s；请返回详情页刷新线路" % selected_flag)
        if not chosen[1]:
            raise RuntimeError("所选线路没有有效播放地址")

        return {
            "parse": 0,
            "playUrl": "",
            "url": chosen[1],
            "header": chosen[2],
        }

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|m4v|mpd|webm)(?:$|[?#])", str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None


spider = Spider()
