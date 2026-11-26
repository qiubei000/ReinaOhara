# -*- coding: utf-8 -*-
"""别催了 TVBox · Python 爬虫：51暗网（51aw.com）

站点：Typecho + Mirages 主题（与 mahuax 同模板族），服务端直出 HTML。
- 站点被 CloudFront 前置，国内部分线路会按 SNI 直接 RST；本源对 51aw.com 的
  请求统一走「CloudFront 主机名当 SNI + Host: 51aw.com」的绕过方式，
  失败再退回普通直连。
- 分类：导航 21 个 /category/<slug>/，翻页 /category/<slug>/<N>/
- 首页：/ 最新，翻页 /page/<N>/
- 卡片：article 内 meta[itemprop=url] → /archives/<id>/，
        h2.post-card-title 标题，loadBannerDirect('<封面>')、post-card-info 日期/分类
- 详情：/archives/<id>/，h1.post-title + meta description，
        正文里可有多集 <div class="dplayer" data-config='...'>，
        JSON 的 video.url 即 m3u8（hls.ohjzmm.cn，auth_key 当天过期，
        所以详情只给文章地址 + ?aw_ep=N，playerContent 现场解析）
- 搜索：/search/<词>/，翻页 /search/<词>/<N>/
- 封面：pic.gyezbp.cn 的 jpg 是 AES-128-CBC 密文（海角同款 key/iv），
        本源纯 Python 解密，本机 127.0.0.1 临时端口懒加载图床
        （bind 0 随机端口，绑定失败时封面回退原图直链）
- 播放：AES-128 HLS，crypt.key 与分片均在 tx.doudou520.online，直连 200

别催了壳导入：
  1. 本文件放到配置根目录 py/ 下
  2. 配置加：
     {"key":"aw","name":"51暗网","type":4,"api":"aw",
      "searchable":1,"quickSearch":0,"filterable":0}
"""

import hashlib
import html as _html
import http.client
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

BASE = "https://51aw.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
# 封面解密图床：不固定端口，bind 0 由系统分临时端口（固定端口在
# WebHomeTV/多开环境下容易被占，绑定失败就全站没封面）
CF_SNI = "dy9lmpl409uuf.cloudfront.net"
SITE_HOSTS = ("51aw.com", "www.51aw.com")
PER_PAGE = 20

MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

CATS = [
    ("jrrg", "今日吃瓜"),
    ("qwrs", "全网热搜"),
    ("awcg", "暗网爆料"),
    ("tanhua", "探花偷拍"),
    ("aidj", "AI短剧"),
    ("mrds", "每日大赛"),
    ("meiri-top", "每日top"),
    ("cunzhi", "寸止挑战"),
    ("sxzq", "暗网视频"),
    ("whhj", "网黄合集"),
    ("dywh", "暗网网红"),
    ("fcll", "暗网反差"),
    ("xycg", "暗网校园"),
    ("anwangluanlun", "暗网乱伦"),
    ("awdz", "暗网AV解说"),
    ("awlq", "暗网猎奇"),
    ("sjb", "暗网怪谈"),
    ("dark-history", "暗史档案"),
    ("dmtt", "动漫天堂"),
    ("hwaw", "海外大片"),
]

try:
    _CTX = ssl.create_default_context()
    _CTX.check_hostname = False
    _CTX.verify_mode = ssl.CERT_NONE
except Exception:
    _CTX = None

_CF_IP = [None]


def _cf_ip():
    if _CF_IP[0] is None:
        try:
            _CF_IP[0] = socket.gethostbyname(CF_SNI)
        except Exception:
            _CF_IP[0] = ""
    return _CF_IP[0]


class _Conn(http.client.HTTPSConnection):
    def __init__(self, host, ip, sni, **kw):
        http.client.HTTPSConnection.__init__(self, host, **kw)
        self._ip = ip
        self._sni = sni

    def connect(self):
        self.sock = socket.create_connection((self._ip, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._sni)


def _fetch(url, referer=BASE + "/", redirects=3):
    url = _html.unescape(url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        url = BASE + ("" if url.startswith("/") else "/") + url
    for _ in range(redirects + 1):
        p = urllib.parse.urlparse(url)
        path = (p.path or "/") + ("?" + p.query if p.query else "")
        headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*",
                   "Accept-Language": "zh-CN,zh;q=0.9", "Referer": referer}
        ip = _cf_ip() if p.hostname in SITE_HOSTS else ""
        try:
            if ip:
                c = _Conn(p.hostname, ip, CF_SNI, timeout=TIMEOUT, context=_CTX)
                headers["Host"] = p.hostname
                c.request("GET", path, headers=headers)
                r = c.getresponse()
                body = r.read()
                loc = r.getheader("Location")
                c.close()
            else:
                r = urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                           timeout=TIMEOUT, context=_CTX)
                body = r.read()
                loc = r.getheader("Location")
                r.close()
            if loc and 300 <= r.status < 400:
                url = loc if loc.startswith("http") else urllib.parse.urljoin(url, loc)
                continue
            return r.status, body
        except Exception:
            if ip:
                # 退回普通直连
                try:
                    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                               timeout=TIMEOUT, context=_CTX)
                    body = r.read()
                    loc = r.getheader("Location")
                    r.close()
                    if loc and 300 <= r.status < 400:
                        url = loc if loc.startswith("http") else urllib.parse.urljoin(url, loc)
                        continue
                    return r.status, body
                except Exception:
                    return 0, b""
            return 0, b""
    return 0, b""


def _clean(s):
    s = _html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# AES-128-CBC 解密（封面图，海角同款 key/iv）
# ---------------------------------------------------------------------------

_AES_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)
_IS = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _IS[_v] = _i


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11b
        b >>= 1
    return r


_M9 = [_gmul(i, 9) for i in range(256)]
_M11 = [_gmul(i, 11) for i in range(256)]
_M13 = [_gmul(i, 13) for i in range(256)]
_M14 = [_gmul(i, 14) for i in range(256)]
_TD0 = [(_M14[_IS[i]] << 24) | (_M9[_IS[i]] << 16) | (_M13[_IS[i]] << 8) | _M11[_IS[i]]
        for i in range(256)]
_TD1 = [(x >> 8) | ((x & 0xff) << 24) for x in _TD0]
_TD2 = [(x >> 16) | ((x & 0xffff) << 16) for x in _TD0]
_TD3 = [(x >> 24) | ((x & 0xffffff) << 8) for x in _TD0]


def _word(w):
    return (w[0] << 24) | (w[1] << 16) | (w[2] << 8) | w[3]


def _invmix_word(x):
    a, b, c, d = (x >> 24) & 255, (x >> 16) & 255, (x >> 8) & 255, x & 255
    return (((_M14[a] ^ _M11[b] ^ _M13[c] ^ _M9[d]) << 24) |
            ((_M9[a] ^ _M14[b] ^ _M11[c] ^ _M13[d]) << 16) |
            ((_M13[a] ^ _M9[b] ^ _M14[c] ^ _M11[d]) << 8) |
            (_M11[a] ^ _M13[b] ^ _M9[c] ^ _M14[d]))


def _dec_schedule(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= rcon
            rcon = _gmul(rcon, 2)
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    dk = [0] * 44
    for j in range(4):
        dk[j] = _word(w[40 + j])
    for i in range(1, 10):
        for j in range(4):
            dk[4 * i + j] = _invmix_word(_word(w[4 * (10 - i) + j]))
    for j in range(4):
        dk[40 + j] = _word(w[j])
    return dk


def _decrypt_block(block, dk):
    w0 = int.from_bytes(block[0:4], "big") ^ dk[0]
    w1 = int.from_bytes(block[4:8], "big") ^ dk[1]
    w2 = int.from_bytes(block[8:12], "big") ^ dk[2]
    w3 = int.from_bytes(block[12:16], "big") ^ dk[3]
    for r in range(1, 10):
        o = 4 * r
        a0 = (_TD0[(w0 >> 24) & 255] ^ _TD1[(w3 >> 16) & 255] ^
              _TD2[(w2 >> 8) & 255] ^ _TD3[w1 & 255] ^ dk[o])
        a1 = (_TD0[(w1 >> 24) & 255] ^ _TD1[(w0 >> 16) & 255] ^
              _TD2[(w3 >> 8) & 255] ^ _TD3[w2 & 255] ^ dk[o + 1])
        a2 = (_TD0[(w2 >> 24) & 255] ^ _TD1[(w1 >> 16) & 255] ^
              _TD2[(w0 >> 8) & 255] ^ _TD3[w3 & 255] ^ dk[o + 2])
        a3 = (_TD0[(w3 >> 24) & 255] ^ _TD1[(w2 >> 16) & 255] ^
              _TD2[(w1 >> 8) & 255] ^ _TD3[w0 & 255] ^ dk[o + 3])
        w0, w1, w2, w3 = a0, a1, a2, a3
    v0 = ((_IS[(w0 >> 24) & 255] << 24) ^ (_IS[(w3 >> 16) & 255] << 16) ^
          (_IS[(w2 >> 8) & 255] << 8) ^ _IS[w1 & 255] ^ dk[40])
    v1 = ((_IS[(w1 >> 24) & 255] << 24) ^ (_IS[(w0 >> 16) & 255] << 16) ^
          (_IS[(w3 >> 8) & 255] << 8) ^ _IS[w2 & 255] ^ dk[41])
    v2 = ((_IS[(w2 >> 24) & 255] << 24) ^ (_IS[(w1 >> 16) & 255] << 16) ^
          (_IS[(w0 >> 8) & 255] << 8) ^ _IS[w3 & 255] ^ dk[42])
    v3 = ((_IS[(w3 >> 24) & 255] << 24) ^ (_IS[(w2 >> 16) & 255] << 16) ^
          (_IS[(w1 >> 8) & 255] << 8) ^ _IS[w0 & 255] ^ dk[43])
    return (v0.to_bytes(4, "big") + v1.to_bytes(4, "big") +
            v2.to_bytes(4, "big") + v3.to_bytes(4, "big"))


def _unpad(b):
    if b and 1 <= b[-1] <= 16 and len(b) >= b[-1]:
        return b[:-b[-1]]
    return b


def _aes_cbc_decrypt(data, key, iv):
    dk = _dec_schedule(key)
    out = bytearray()
    prev = iv
    n = len(data) - len(data) % 16
    for i in range(0, n, 16):
        blk = data[i:i + 16]
        dec = _decrypt_block(blk, dk)
        out.extend(dec[j] ^ prev[j] for j in range(16))
        prev = blk
    return _unpad(bytes(out))


def _looks_image(b):
    return bool(b) and (b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or
                        b[:4] == b"GIF8" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP"))


def _img_mime(b):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] == b"GIF8":
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _decrypt_image(raw):
    if not raw:
        return b""
    if _looks_image(raw):
        return raw
    try:
        out = _aes_cbc_decrypt(raw, MEDIA_KEY, MEDIA_IV)
    except Exception:
        return b""
    return out if _looks_image(out) else b""


# ---------------------------------------------------------------------------
# 封面本地图床
# ---------------------------------------------------------------------------

_PIC_DIR = [None]
_PIC_MEM = {}
_PIC_LOCK = threading.Lock()


def _pic_dir():
    if _PIC_DIR[0] is not None:
        return _PIC_DIR[0]
    cands = []
    try:
        cands.append(os.path.join(tempfile.gettempdir(), "aw_pic"))
    except Exception:
        pass
    try:
        cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_aw_pic"))
    except Exception:
        pass
    cands += ["/sdcard/TVBox/aw_pic", "/sdcard/Download/aw_pic"]
    _PIC_DIR[0] = ""
    for d in cands:
        try:
            if not os.path.isdir(d):
                os.makedirs(d)
            t = os.path.join(d, ".w")
            with open(t, "wb") as f:
                f.write(b"1")
            os.remove(t)
            _PIC_DIR[0] = d
            break
        except Exception:
            continue
    return _PIC_DIR[0]


def _pic_fetch(url):
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    with _PIC_LOCK:
        if key in _PIC_MEM:
            return _PIC_MEM[key]
    d = _pic_dir()
    path = os.path.join(d, key + ".img") if d else ""
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if _looks_image(data):
                _PIC_MEM[key] = data
                return data
        except Exception:
            pass
    h = {"User-Agent": UA, "Referer": BASE + "/", "Accept": "image/*,*/*"}
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=h),
                                     timeout=40, context=_CTX).read()
    except Exception:
        raw = b""
    data = _decrypt_image(raw)
    if data:
        _PIC_MEM[key] = data
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(data)
            except Exception:
                pass
    return data


def _pic_url(url):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    srv = _pic_server()
    if srv and _PIC_PORT[0]:
        return "http://127.0.0.1:%d/img?u=%s" % (_PIC_PORT[0], urllib.parse.quote(url, safe=""))
    # 图床起不来时回退原图直链，不要让封面 404 全灭
    return url


class _PicHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = urllib.parse.urlparse(self.path)
            if q.path != "/img":
                self.send_response(404)
                self.end_headers()
                return
            u = urllib.parse.parse_qs(q.query).get("u", [""])[0]
            data = _pic_fetch(u) if u else b""
            if not data:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", _img_mime(data))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            pass

    def log_message(self, *a):
        pass


class _ThreadHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_PIC_SERVER = [None]
_PIC_PORT = [0]
_PIC_LOCK = threading.Lock()


def _pic_server():
    if _PIC_SERVER[0] is not None:
        return _PIC_SERVER[0]
    with _PIC_LOCK:
        if _PIC_SERVER[0] is not None:
            return _PIC_SERVER[0]
        try:
            # bind 0：系统分临时端口，避免固定端口被占导致起不来
            srv = _ThreadHTTPServer(("127.0.0.1", 0), _PicHandler)
            t = threading.Thread(target=srv.serve_forever)
            t.daemon = True
            t.start()
            _PIC_PORT[0] = srv.server_address[1]
            _PIC_SERVER[0] = srv
        except Exception:
            _PIC_SERVER[0] = False
            _PIC_PORT[0] = 0
    return _PIC_SERVER[0]


# ---------------------------------------------------------------------------
# 列表 / 详情
# ---------------------------------------------------------------------------

def _pagecount(html, pg, count):
    ms = re.findall(r'max="(\d+)"', html)
    if ms:
        try:
            return max(int(ms[0]), pg)
        except Exception:
            pass
    m = re.search(r'page-current">\s*\d+\s*/\s*(\d+)', html)
    if m:
        try:
            return max(int(m.group(1)), pg)
        except Exception:
            pass
    return pg + 1 if count >= PER_PAGE else pg


def _cards(html):
    out = []
    seen = set()
    for m in re.finditer(r"(?s)<article\b(.*?)</article>", html):
        blk = m.group(1)
        if 'class="ad-item"' in blk[:200] or "ad-item" in blk[:100]:
            continue
        lm = re.search(r'itemprop="url mainEntityOfPage" content="([^"]+)"', blk)
        if not lm:
            lm = re.search(r'href="(/archives/\d+/)"', blk)
        if not lm:
            continue
        path = lm.group(1)
        if path in seen:
            continue
        tm = re.search(r'class="post-card-title"[^>]*>(.*?)</h2>', blk, re.S)
        name = _clean(re.sub(r"<span[^>]*>.*?</span>", "", tm.group(1), flags=re.S)) if tm else ""
        name = re.sub(r"^(热搜\s*HOT|置顶|推荐)\s*", "", name)
        if not name:
            continue
        pm = re.search(r"loadBannerDirect\('([^']+)'", blk)
        pic = pm.group(1) if pm else ""
        marks = []
        dm = re.search(r'itemprop="datePublished" content="([^"]+)"', blk)
        if dm:
            marks.append(dm.group(1)[:10])
        cm = re.search(r'class="post-card-info"(.*?)</div>', blk, re.S)
        if cm:
            spans = re.findall(r"<span[^>]*>(.*?)</span>", cm.group(1), re.S)
            if spans:
                cat = _clean(spans[-1]).strip("• ")
                if cat:
                    marks.append(cat)
        seen.add(path)
        out.append({"vod_id": path, "vod_name": name, "vod_pic": _pic_url(pic),
                    "vod_remarks": " · ".join([x for x in marks if x])})
    return out


def _play_configs(html):
    urls = []
    for m in re.finditer(r"data-config='([^']*)'", html):
        try:
            d = json.loads(_html.unescape(m.group(1)))
        except Exception:
            continue
        v = d.get("video")
        if isinstance(v, dict):
            u = v.get("url") or ""
            if u and ".m3u8" in u or (u and u.startswith("http")):
                urls.append(_html.unescape(u))
    return urls


def _detail(path):
    path = _html.unescape(str(path or "")).strip()
    if path.startswith("http"):
        path = urllib.parse.urlparse(path).path
    if not path.startswith("/"):
        path = "/archives/%s/" % path.strip("/")
    if not path.endswith("/"):
        path += "/"
    page = BASE + path
    st, b = _fetch(page)
    if not b:
        return None
    html = b.decode("utf-8", "replace")
    tm = re.search(r'(?s)class="post-title"[^>]*>(.*?)</h1>', html)
    name = _clean(tm.group(1)) if tm else ""
    if not name:
        t = re.search(r"(?s)<title>(.*?)</title>", html)
        name = _clean(t.group(1)).split(" - ")[0] if t else path
    pm = re.findall(r"(?:https?:)?//pic\.gyezbp\.cn[^'\"\\\s>]+", html)
    pic = ""
    if pm:
        pic = pm[0]
        if pic.startswith("//"):
            pic = "https:" + pic
    if not pic:
        lm = re.search(r"loadBannerDirect\('([^']+)'", html)
        pic = lm.group(1) if lm else ""
    dm = re.search(r'name="description" content="([^"]*)"', html)
    desc = _clean(dm.group(1)) if dm else ""
    am = re.search(r'itemprop="name" content="([^"]*)"', html)
    author = _clean(am.group(1)) if am else ""
    dt = re.search(r'itemprop="datePublished" content="([^"]+)"', html)
    date = dt.group(1)[:10] if dt else ""
    urls = _play_configs(html)
    lines = []
    if desc:
        lines.append(desc)
    if author:
        lines.append("作者：" + author)
    if date:
        lines.append("日期：" + date)
    eps = []
    if not urls:
        play = ""
    elif len(urls) == 1:
        play = "正片$" + page + "?aw_ep=0"
    else:
        eps = ["第%d集$%s?aw_ep=%d" % (i + 1, page, i) for i in range(len(urls))]
        play = "#".join(eps)
    vod = {"vod_id": path, "vod_name": name, "vod_pic": _pic_url(pic),
           "vod_remarks": (date + " · " if date else "") + ("%d集" % len(urls) if urls else "图文"),
           "vod_content": "\n".join(lines), "vod_play_from": "51暗网",
           "vod_play_url": play}
    return vod


class Spider(object):

    def __init__(self):
        self.api = ""

    def init(self, *args, **kwargs):
        if args:
            self.api = args[0]
        _pic_server()

    def homeContent(self, *args, **kwargs):
        _pic_server()
        classes = [{"type_id": k, "type_name": n} for k, n in CATS]
        vlist = []
        try:
            st, b = _fetch(BASE + "/")
            vlist = _cards(b.decode("utf-8", "replace"))
        except Exception:
            pass
        return {"class": classes, "filters": {}, "list": vlist}

    def homeVideoContent(self, *args, **kwargs):
        try:
            st, b = _fetch(BASE + "/")
            return {"list": _cards(b.decode("utf-8", "replace"))}
        except Exception:
            return {"list": []}

    def categoryContent(self, *args, **kwargs):
        _pic_server()
        tid = str(args[0] if args else kwargs.get("tid", "")).strip("/")
        try:
            pg = int(args[1] if len(args) > 1 else kwargs.get("pg", 1))
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        url = "%s/category/%s/" % (BASE, tid)
        if pg > 1:
            url += "%d/" % pg
        try:
            st, b = _fetch(url)
        except Exception:
            b = b""
        html = b.decode("utf-8", "replace")
        vlist = _cards(html)
        return {"page": pg, "pagecount": _pagecount(html, pg, len(vlist)),
                "limit": len(vlist) or PER_PAGE,
                "total": 999999 if vlist else 0, "list": vlist}

    def detailContent(self, *args, **kwargs):
        _pic_server()
        raw = args[0] if args else kwargs.get("ids", [])
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        vid = str(raw).strip()
        if not vid:
            return {"list": []}
        try:
            vod = _detail(vid)
        except Exception:
            vod = None
        if not vod:
            return {"list": []}
        return {"list": [vod]}

    def playerContent(self, *args, **kwargs):
        pid = str(args[1] if len(args) > 1 else kwargs.get("id", "")).strip()
        if not pid:
            return {"parse": 0, "url": "", "header": {}, "flag": "51暗网"}
        if ".m3u8" in pid:
            return {"parse": 0, "playUrl": "", "url": pid,
                    "header": {"User-Agent": UA, "Referer": BASE + "/"}, "flag": "51暗网"}
        ep = 0
        m = re.search(r"[?&]aw_ep=(\d+)", pid)
        if m:
            ep = int(m.group(1))
        page = re.sub(r"[?&]aw_ep=\d+", "", pid)
        url = ""
        try:
            st, b = _fetch(page)
            urls = _play_configs(b.decode("utf-8", "replace"))
            if urls:
                url = urls[ep] if 0 <= ep < len(urls) else urls[0]
        except Exception:
            url = ""
        return {"parse": 0, "playUrl": "", "url": url or pid,
                "header": {"User-Agent": UA, "Referer": BASE + "/"}, "flag": "51暗网"}

    def searchContent(self, *args, **kwargs):
        _pic_server()
        key = str(args[0] if args else kwargs.get("key", "")).strip()
        pg = 1
        if len(args) >= 3:
            try:
                pg = int(args[2])
            except Exception:
                pg = 1
        elif len(args) == 2:
            try:
                pg = int(args[1])
            except Exception:
                pg = 1
        if pg < 1:
            pg = 1
        if not key:
            return {"page": pg, "pagecount": pg, "limit": PER_PAGE, "total": 0, "list": []}
        url = "%s/search/%s/" % (BASE, urllib.parse.quote(key.encode("utf-8")))
        if pg > 1:
            url += "%d/" % pg
        try:
            st, b = _fetch(url)
        except Exception:
            b = b""
        html = b.decode("utf-8", "replace")
        vlist = _cards(html)
        return {"page": pg, "pagecount": _pagecount(html, pg, len(vlist)),
                "limit": len(vlist) or PER_PAGE,
                "total": 999999 if vlist else 0, "list": vlist}

    def searchContentPage(self, *args, **kwargs):
        return self.searchContent(*args, **kwargs)
