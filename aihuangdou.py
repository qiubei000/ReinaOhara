# coding=utf-8
# 黄桃短剧 https://aihuangdou.com/
# 封面 AES 解密（localProxy）+ 播放鉴权

import re
import json
import base64
from urllib.parse import quote, unquote
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    host = "https://aihuangdou.com"

    cate_list = [
        {"type_id": "ai-duanju", "type_name": "🎬 AI短剧"},
        {"type_id": "ai-manju", "type_name": "🎞 AI漫剧"},
        {"type_id": "ai-mogai", "type_name": "✨ AI魔改"},
        {"type_id": "ai-meinv", "type_name": "💃 AI美女"},
        {"type_id": "updates", "type_name": "🆕 最新更新"},
        {"type_id": "rankings", "type_name": "🔥 今日热播"},
        {"type_id": "topics", "type_name": "📚 专题合集"},
        {"type_id": "tags", "type_name": "🏷 热门标签"},
    ]

    def init(self, extend=""):
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self._img_key = "f5d965df75336270"
        self._img_iv = "97b60394abc2fbe1"
        self._load_img_keys()

    def homeContent(self, filter):
        return {"class": self.cate_list}

    def homeVideoContent(self):
        try:
            return self._get_list(self.host + "/", "1")
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            if not pg or str(pg) in ("0", "None"):
                pg = "1"
            pg = str(pg)
            tid = str(tid).strip().strip("/")

            if tid.startswith("tag/"):
                slug = tid[4:].strip("/")
                base = f"{self.host}/tags/{quote(slug)}/"
                url = base if pg == "1" else f"{self.host}/tags/{quote(slug)}/{pg}/"
                return self._get_list(url, pg)

            if tid.startswith("topic/"):
                slug = tid[6:].strip("/")
                base = f"{self.host}/topic/{slug}/"
                url = base if pg == "1" else f"{self.host}/topic/{slug}/{pg}/"
                return self._get_list(url, pg)

            if tid == "tags":
                return self._get_tags(pg)
            if tid == "topics":
                return self._get_topics(pg)

            if pg == "1":
                url = f"{self.host}/{tid}/"
            else:
                url = f"{self.host}/{tid}/{pg}/"
            return self._get_list(url, pg)
        except Exception:
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            if not pg or str(pg) in ("0", "None"):
                pg = "1"
            pg = str(pg)
            q = quote(key)
            url = f"{self.host}/search/?q={q}" if pg == "1" else f"{self.host}/search/{pg}/?q={q}"
            return self._get_list(url, pg)
        except Exception:
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, ids):
        try:
            raw = str(ids[0]).strip()
            m = re.search(r"(\d+)", raw)
            if not m:
                return {"list": []}
            did = m.group(1)
            url = f"{self.host}/drama/{did}/"
            html = self.fetch(url)
            if not html:
                return {"list": []}

            title = self._re(r"<title>([^<\-|]+)", html) or self._re(r"查看《([^》]+)》", html) or did
            title = re.sub(r"\s+", " ", title).strip()

            pic = self._re(r'property="og:image"\s+content="(https?://[^"]+)"', html) or ""
            if not pic:
                pic = self._re(r'"poster"\s*:\s*"(https?://[^"]+)"', html) or ""
            if not pic:
                pic = self._re(r'data-src="(https?://pic\.qnlycc\.cn/[^"]+)"', html) or ""
            pic = self._pic_proxy(pic)

            desc = self._re(r'property="og:description"\s+content="([^"]+)"', html) or ""
            if not desc:
                desc = self._re(r'"description"\s*:\s*"([^"]{10,400})"', html) or ""
            desc = desc.replace("\\n", "\n").strip()

            type_name = self._re(r'channelURL"\s*:\s*"/([^"]+)/"', html) or ""
            type_map = {
                "ai-duanju": "AI短剧",
                "ai-manju": "AI漫剧",
                "ai-mogai": "AI魔改",
                "ai-meinv": "AI美女",
            }
            type_name = type_map.get(type_name, type_name or "黄桃短剧")

            found = {}
            grid = re.search(r'id="nineEpisodeGrid"[^>]*>([\s\S]*?)</div>', html)
            block = grid.group(1) if grid else html
            for em in re.finditer(
                rf'href="(/video/{did}/(?:(\d+)/)?)"[^>]*(?:title="([^"]*)")?',
                block,
            ):
                num = em.group(2)
                n = int(num) if num else 1
                if n in found:
                    continue
                etitle = (em.group(3) or "").strip()
                name = etitle if etitle.startswith("第") else f"第{n}集"
                found[n] = name

            if not found:
                for em in re.finditer(
                    rf'"n"\s*:\s*(\d+)[^}}]{{0,80}}"url"\s*:\s*"/video/{did}/',
                    html,
                ):
                    n = int(em.group(1))
                    found[n] = f"第{n}集"

            if not found:
                found[1] = "第1集"

            # 用 # 与 $ 分隔；集号单独放，避免客户端拆错
            play_parts = [f"{found[n]}${did}_{n}" for n in sorted(found.keys())]
            play_url = "#".join(play_parts)

            return {"list": [{
                "vod_id": did,
                "vod_name": title,
                "vod_pic": pic,
                "type_name": type_name,
                "vod_year": self._re(r'"yearText"\s*:\s*"(\d+)"', html) or "",
                "vod_area": "网络",
                "vod_remarks": f"{len(found)}集",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": desc or title,
                "vod_play_from": "黄桃线路",
                "vod_play_url": play_url,
            }]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            raw = str(id).strip()
            # 支持 34190_1 / 34190$1 / 纯数字
            did, ep = "0", "1"
            if "_" in raw:
                did, ep = raw.split("_", 1)
            elif "$" in raw:
                parts = raw.split("$")
                did, ep = parts[0], parts[-1]
            else:
                m = re.search(r"(\d+)", raw)
                if m:
                    did = m.group(1)

            did = re.sub(r"\D", "", did) or "0"
            ep = re.sub(r"\D", "", str(ep)) or "1"

            play, cdn_auth = self._get_playback(did, ep)
            headers = {
                "User-Agent": self.header["User-Agent"],
                "Referer": f"{self.host}/video/{did}/",
                "Origin": self.host,
                "Accept": "*/*",
            }
            if cdn_auth:
                headers["x-cdn-auth"] = cdn_auth

            if not play:
                # 兜底：返回剧集页让壳嗅探（部分壳可用）
                return {
                    "parse": 1,
                    "url": f"{self.host}/video/{did}/" + ("" if ep == "1" else f"{ep}/"),
                    "header": headers,
                }

            return {
                "parse": 0,
                "url": play,
                "header": headers,
            }
        except Exception:
            return {"parse": 0, "url": "", "header": self.header}

    def localProxy(self, param):
        """解密 AES-128-CBC 封面，供列表/详情显示"""
        try:
            url = param.get("url") or param.get("src") or ""
            if not url:
                return [404, "text/plain", b""]
            url = unquote(url)
            if url.startswith("//"):
                url = "https:" + url

            headers = {
                "User-Agent": self.header["User-Agent"],
                "Referer": self.host + "/",
            }
            data = self._http_bytes(url, headers)
            if not data:
                return [404, "text/plain", b""]

            # 已是正常图片
            if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (
                data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            ):
                mime = "image/jpeg"
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    mime = "image/png"
                elif data[:4] == b"RIFF":
                    mime = "image/webp"
                return [200, mime, data]

            plain = self._decrypt_image(data)
            if not plain:
                return [404, "text/plain", b""]
            mime = "image/jpeg"
            if plain[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            elif plain[:4] == b"RIFF":
                mime = "image/webp"
            return [200, mime, plain]
        except Exception:
            return [404, "text/plain", b""]

    # ---------- 内部 ----------

    def _load_img_keys(self):
        try:
            html = self.fetch(self.host + "/")
            m = re.search(r'"imgEncKey"\s*:\s*"([^"]+)"', html or "")
            if m and len(m.group(1)) == 16:
                self._img_key = m.group(1)
            m = re.search(r'"imgEncIV"\s*:\s*"([^"]+)"', html or "")
            if m and len(m.group(1)) == 16:
                self._img_iv = m.group(1)
        except Exception:
            pass

    def _decrypt_image(self, data):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            key = self._img_key.encode("utf-8")
            iv = self._img_iv.encode("utf-8")
            if len(key) != 16 or len(iv) != 16:
                return b""
            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            plain = decryptor.update(data) + decryptor.finalize()
            if plain and plain[-1] <= 16:
                pad = plain[-1]
                if pad > 0 and plain.endswith(bytes([pad]) * pad):
                    plain = plain[:-pad]
            return plain
        except Exception:
            return b""

    def _http_bytes(self, url, headers=None):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers or self.header)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception:
            return b""

    def fetch(self, url):
        try:
            if hasattr(self, "net") and self.net:
                r = self.net.get(url, headers=self.header)
                if isinstance(r, str):
                    return r
                if hasattr(r, "text"):
                    return r.text
                return str(r)
        except Exception:
            pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self.header)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _pic_proxy(self, pic):
        """加密图走 localProxy；普通图直链"""
        if not pic:
            return ""
        pic = pic.replace("\\u0026", "&")
        pic = pic.replace("\\/", "/")
        if pic.startswith("//"):
            pic = "https:" + pic
        if not any(h in pic for h in ("qnlycc.cn", "aluxvl.cn")):
            return pic
        try:
            base = ""
            if hasattr(self, "getProxy"):
                try:
                    base = self.getProxy(True) or ""
                except Exception:
                    base = ""
            if base and not str(base).startswith("proxy://"):
                sep = "&" if "?" in str(base) else "?"
                return f"{base}{sep}url={quote(pic, safe='')}"
        except Exception:
            pass
        return f"proxy://do=img&url={quote(pic, safe='')}"


    def _get_playback(self, did, ep):
        api = f"{self.host}/api/videos/{did}/episodes/{ep}/playback"
        headers = {
            **self.header,
            "Referer": f"{self.host}/video/{did}/",
            "Origin": self.host,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            import urllib.request
            req = urllib.request.Request(api, data=b"{}", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            d = data.get("data") or {}
            if not isinstance(d, dict):
                return "", ""
            streams = d.get("streams") or {}
            play = streams.get("main") or d.get("src") or streams.get("preview") or ""
            cdn = d.get("cdn") or {}
            auth = cdn.get("authValue") or ""
            return play, auth
        except Exception:
            return "", ""

    def _get_list(self, url, pg="1"):
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 24, "total": 0}

        items = []
        seen = set()
        used_pics = set()

        for art in re.findall(
            r'<article[^>]*class="[^"]*drama-card[^"]*"[^>]*>([\s\S]*?)</article>',
            html,
        ):
            if "pm-ssp-slot" in art or "data-ssp-shell" in art:
                continue
            hm = re.search(r'href="(/drama/(\d+)/)"', art)
            if not hm:
                continue
            did = hm.group(2)
            if did in seen:
                continue
            seen.add(did)

            name = ""
            nm = re.search(r"查看《([^》]+)》", art)
            if nm:
                name = nm.group(1).strip()
            if not name:
                nm = re.search(r'alt="《([^》]+)》', art)
                if nm:
                    name = nm.group(1).strip()
            if not name:
                nm = re.search(r'alt="([^"]+)"', art)
                if nm:
                    name = nm.group(1).replace("封面", "").strip()
            if not name:
                name = f"作品{did}"

            pic = ""
            for pm in re.finditer(r'data-src="(https?://[^"]+)"', art):
                u = pm.group(1)
                if "loading" in u or "/static/" in u:
                    continue
                pic = u
                break
            if not pic:
                for pm in re.finditer(r'src="(https?://[^"]+\.(?:jpeg|jpg|png|webp)[^"]*)"', art):
                    u = pm.group(1)
                    if "loading" in u or "/static/" in u:
                        continue
                    pic = u
                    break

            # 封面去重（按路径）
            base = pic.split("?")[0] if pic else ""
            if base and base in used_pics:
                pic = ""
            elif base:
                used_pics.add(base)

            pic = self._pic_proxy(pic)

            remarks = ""
            rm = re.search(r"(更新至\s*\d+\s*集|\d+\s*集|连载|完结)", art)
            if rm:
                remarks = rm.group(1).replace(" ", "")

            items.append({
                "vod_id": did,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })

        if not items:
            for m in re.finditer(r'href="(/drama/(\d+)/)"[^>]*>[\s\S]{0,120}?《([^》]+)》', html):
                did, name = m.group(2), m.group(3).strip()
                if did in seen:
                    continue
                seen.add(did)
                items.append({
                    "vod_id": did,
                    "vod_name": name,
                    "vod_pic": "",
                    "vod_remarks": "",
                })

        pagecount = 1
        pm = re.search(r"第\s*\d+\s*/\s*(\d+)\s*页", html)
        if pm:
            try:
                pagecount = int(pm.group(1))
            except Exception:
                pagecount = 1
        else:
            pm = re.search(r'data-pages="(\d+)"', html)
            if pm:
                try:
                    pagecount = int(pm.group(1))
                except Exception:
                    pagecount = 1
            elif "下一页" in html or 'pager-dir="next"' in html:
                try:
                    pagecount = max(int(pg) + 3, 10)
                except Exception:
                    pagecount = 10

        return {
            "list": items,
            "page": int(pg),
            "pagecount": max(pagecount, 1),
            "limit": 24,
            "total": max(pagecount, 1) * 24,
        }

    def _get_tags(self, pg="1"):
        html = self.fetch(f"{self.host}/tags/")
        if not html:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 50, "total": 0}
        items, seen = [], set()
        for m in re.finditer(r'href="(/tags/([^"/]+)/?)"[^>]*>([^<]+)', html):
            slug, name = m.group(2), re.sub(r"\s+", " ", m.group(3)).strip()
            if not name or slug in seen:
                continue
            seen.add(slug)
            items.append({
                "vod_id": f"tag/{slug}",
                "vod_name": f"🏷 {name}",
                "vod_pic": "",
                "vod_remarks": "标签",
                "vod_tag": "folder",
                "style": {"type": "list"},
            })
        return {"list": items, "page": 1, "pagecount": 1, "limit": len(items) or 50, "total": len(items)}

    def _get_topics(self, pg="1"):
        html = self.fetch(f"{self.host}/topics/")
        if not html:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 50, "total": 0}
        items, seen = [], set()
        for m in re.finditer(r'href="(/topic/([^"/]+)/)"[^>]*>[\s\S]{0,80}?([^<]{2,30})', html):
            slug, name = m.group(2), re.sub(r"\s+", " ", m.group(3)).strip()
            if not name or slug in seen or len(name) > 30:
                continue
            seen.add(slug)
            items.append({
                "vod_id": f"topic/{slug}",
                "vod_name": f"📚 {name}",
                "vod_pic": "",
                "vod_remarks": "专题",
                "vod_tag": "folder",
                "style": {"type": "list"},
            })
        return {"list": items, "page": 1, "pagecount": 1, "limit": len(items) or 50, "total": len(items)}

    def _re(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ""
