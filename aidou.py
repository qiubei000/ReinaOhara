# -*- coding: utf-8 -*-
import base64
import json
import threading as _th
import time
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler as _BHR, ThreadingHTTPServer as _THS
from urllib.parse import urlparse as _up, parse_qs as _pqs, quote as _quote, unquote as _unquote


BASE = "https://ww7.aida3.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
PAGE_SIZE = 20

# 分类: type_id -> (名称, API 参数)
CATS = [
    ("new", "最近更新", {"by": "vod_time"}),
    ("hot", "热门", {"by": "vod_hits"}),
    ("good", "精选", {"by": "vod_score"}),
    ("1", "国产", {"type": "1", "by": "vod_time"}),
    ("5", "传媒", {"type": "5", "by": "vod_time"}),
    ("2", "日韩", {"type": "2", "by": "vod_time"}),
    ("3", "欧美", {"type": "3", "by": "vod_time"}),
    ("4", "动漫", {"type": "4", "by": "vod_time"}),
    ("6", "免费", {"type": "6", "by": "vod_time"}),
]
_CAT_MAP = {c[0]: c[2] for c in CATS}


# ================= 纯 Python AES-128 =================
def _init_sbox():
    p = q = 1
    sbox = [0] * 256
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) & 0xFF ^ ((q << 2) | (q >> 6)) & 0xFF \
            ^ ((q << 3) | (q >> 5)) & 0xFF ^ ((q << 4) | (q >> 4)) & 0xFF
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
        if p == 0:
            p = 1
    sbox[0] = 0x63
    return sbox


_SBOX = None
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D]
_INV_SBOX = None
_MUL = None


def _get_sbox():
    global _SBOX
    if _SBOX is None:
        _SBOX = _init_sbox()
    return _SBOX


def _get_inv_sbox():
    global _INV_SBOX
    if _INV_SBOX is None:
        sbox = _get_sbox()
        inv = [0] * 256
        for i, v in enumerate(sbox):
            inv[v] = i
        _INV_SBOX = inv
    return _INV_SBOX


def _xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1) & 0xFF


def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _get_mul_tables():
    global _MUL
    if _MUL is None:
        _MUL = {m: [_gmul(x, m) for x in range(256)] for m in (9, 11, 13, 14)}
    return _MUL


def _aes128_key_expand(key):
    sbox = _get_sbox()
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [sbox[b] for b in t]
            t[0] ^= _RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    return [bytes(sum(w[i * 4:(i + 1) * 4], [])) for i in range(11)]


def _aes128_encrypt_block(rk, block):
    sbox = _get_sbox()
    s = [block[4 * c + r] for c in range(4) for r in range(4)]

    def add_rk(n):
        for i in range(16):
            s[i] ^= rk[n][i]

    def sub():
        for i in range(16):
            s[i] = sbox[s[i]]

    def shift():
        t = s[:]
        for r in range(4):
            for c in range(4):
                s[4 * c + r] = t[4 * ((c + r) % 4) + r]

    def mix():
        for c in range(4):
            a = s[4 * c:4 * c + 4]
            s[4 * c + 0] = _xtime(a[0]) ^ (_xtime(a[1]) ^ a[1]) ^ a[2] ^ a[3]
            s[4 * c + 1] = a[0] ^ _xtime(a[1]) ^ (_xtime(a[2]) ^ a[2]) ^ a[3]
            s[4 * c + 2] = a[0] ^ a[1] ^ _xtime(a[2]) ^ (_xtime(a[3]) ^ a[3])
            s[4 * c + 3] = (_xtime(a[0]) ^ a[0]) ^ a[1] ^ a[2] ^ _xtime(a[3])

    add_rk(0)
    for rnd in range(1, 10):
        sub()
        shift()
        mix()
        add_rk(rnd)
    sub()
    shift()
    add_rk(10)
    return bytes(s[c * 4 + r] for c in range(4) for r in range(4))


def _aes128_decrypt_block(rk, block):
    inv = _get_inv_sbox()
    s = [block[4 * c + r] for c in range(4) for r in range(4)]

    def add_rk(n):
        for i in range(16):
            s[i] ^= rk[n][i]

    def inv_sub():
        for i in range(16):
            s[i] = inv[s[i]]

    def inv_shift():
        t = s[:]
        for r in range(4):
            for c in range(4):
                s[4 * c + r] = t[4 * ((c - r) % 4) + r]

    def inv_mix():
        t = _get_mul_tables()
        m9, m11, m13, m14 = t[9], t[11], t[13], t[14]
        for c in range(4):
            o = 4 * c
            a0, a1, a2, a3 = s[o], s[o + 1], s[o + 2], s[o + 3]
            s[o] = m14[a0] ^ m11[a1] ^ m13[a2] ^ m9[a3]
            s[o + 1] = m9[a0] ^ m14[a1] ^ m11[a2] ^ m13[a3]
            s[o + 2] = m13[a0] ^ m9[a1] ^ m14[a2] ^ m11[a3]
            s[o + 3] = m11[a0] ^ m13[a1] ^ m9[a2] ^ m14[a3]

    add_rk(10)
    for rnd in range(9, 0, -1):
        inv_shift()
        inv_sub()
        add_rk(rnd)
        inv_mix()
    inv_shift()
    inv_sub()
    add_rk(0)
    return bytes(s[c * 4 + r] for c in range(4) for r in range(4))


def _aes_cbc_encrypt(key, data):
    pad = 16 - len(data) % 16
    data = data + bytes([pad]) * pad
    rk = _aes128_key_expand(key)
    out = bytearray()
    prev = key
    for off in range(0, len(data), 16):
        blk = bytes(a ^ b for a, b in zip(data[off:off + 16], prev))
        enc = _aes128_encrypt_block(rk, blk)
        out += enc
        prev = enc
    return bytes(out)


def _aes_cbc_decrypt(key, data):
    if not data or len(data) % 16 != 0:
        return None
    rk = _aes128_key_expand(key)
    out = bytearray()
    prev = key
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        dec = _aes128_decrypt_block(rk, blk)
        out += bytes(a ^ b for a, b in zip(dec, prev))
        prev = blk
    if not out:
        return None
    pad = out[-1]
    if pad < 1 or pad > 16:
        return bytes(out)
    return bytes(out[:-pad])


# ================= API 加密 =================
def _api_key(t):
    # (t*299 + "1") 再反转, Latin1 编码 = 16 字节
    return (str(t * 299) + "1")[::-1].encode("latin1")


def _api_md5(t):
    return format(int((str(t * 177) + "1")[::-1]), "x")


# ================= 封面图片代理 =================
# 封面是字节反转过的 JPEG (站内 JS getCover 反转后显示), 原始 URL 在 OK影视里
# 显示不出来. 蜘蛛内置一个本地 HTTP 服务, vod_pic 改成本地代理地址, 代理取回
# 图片后反转字节, 按真实格式回正确的 Content-Type.
_IMG = {"port": None, "server": None, "lock": _th.Lock()}
_IMG_PORTS = (9980, 9981, 9982, 9983, 9984)


def _img_ct(data, url):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _fetch_pic_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": BASE + "/",
    })
    try:
        import ssl as _ssl2
        _ctx2 = _ssl2.SSLContext(_ssl2.PROTOCOL_TLS_CLIENT)
        _ctx2.check_hostname = False
        _ctx2.verify_mode = _ssl2.CERT_NONE
        try:
            _ctx2.set_alpn_protocols(["http/1.1"])
        except Exception:
            pass
        _op2 = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx2))
    except Exception:
        _op2 = urllib.request.build_opener()
    with _op2.open(req, timeout=timeout) as r:
        return r.read(12 * 1024 * 1024)


def _unreverse_pic(data):
    # 反转字节; 若反转后是真图片则返回, 否则返回 None
    if not data:
        return None
    rev = data[::-1]
    if rev[:3] == b"\xff\xd8\xff" or rev[:8] == b"\x89PNG\r\n\x1a\n" \
            or rev[:6] in (b"GIF87a", b"GIF89a"):
        return rev
    return None


class _ImgHandler(_BHR):
    def log_message(self, *a):
        pass

    def do_GET(self):
        try:
            q = _pqs(_up(self.path).query)
            urls = q.get("url") or []
            if not urls:
                self.send_response(400)
                self.end_headers()
                return
            raw_url = _unquote(urls[0])
            data = _fetch_pic_bytes(raw_url)
            rev = _unreverse_pic(data)
            if rev is not None:
                data = rev
            ct = _img_ct(data, raw_url)
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass


def _ensure_img_server():
    # 返回本地代理端口; 失败返回 None (调用方回退到原图 URL)
    # 固定端口 (9980 起) 而不用随机端口; 绑定 0.0.0.0 而非仅 127.0.0.1.
    if _IMG["port"]:
        return _IMG["port"]
    with _IMG["lock"]:
        if _IMG["port"]:
            return _IMG["port"]
        for port in _IMG_PORTS:
            try:
                srv = _THS(("0.0.0.0", port), _ImgHandler)
                t = _th.Thread(target=srv.serve_forever, daemon=True)
                t.start()
                _IMG["port"] = port
                _IMG["server"] = srv
                return port
            except Exception:
                continue
        return None


def _proxy_pic(url):
    if not url:
        return ""
    port = _ensure_img_server()
    if port:
        return "http://127.0.0.1:%d/img?url=%s" % (port, _quote(url, safe=""))
    return url


class Spider:
    def __init__(self, *args):
        # opener 懒创建: __init__ 里不建, 首次联网时才建
        self.opener = None
        self._cache = {}  # vodId(str) -> row
        # 预启动本地图片代理 (失败也不影响列表/播放, 只是封面回退到原图)
        try:
            _ensure_img_server()
        except Exception:
            pass

    def _opener(self):
        if self.opener is None:
            try:
                import ssl as _ssl
                # 不用 create_default_context(): 加载系统 CA 在 OK影视里可能卡住
                ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                try:
                    ctx.set_alpn_protocols(["http/1.1"])
                except Exception:
                    pass
                self.opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=ctx))
            except Exception:
                self.opener = urllib.request.build_opener()
        return self.opener

    def _post(self, url, body, timeout=20):
        req = urllib.request.Request(url, data=body, headers={
            "User-Agent": UA,
            "Referer": BASE + "/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }, method="POST")
        with self._opener().open(req, timeout=timeout) as r:
            return r.read()

    def _api(self, path, params, timeout=20):
        """调用 /awsapi/<path>, 返回解密后的 data dict, 失败返回 None"""
        try:
            t = int(time.time() * 1000)
            key = _api_key(t)
            payload = json.dumps(params, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")
            enc = base64.b64encode(_aes_cbc_encrypt(key, payload)).decode()
            body = urllib.parse.urlencode({"data": enc}).encode()
            url = BASE + "/awsapi" + path + "?md5=" + _api_md5(t)
            raw = self._post(url, body, timeout=timeout)
            resp = json.loads(raw.decode("utf-8", "ignore"))
            if resp.get("code") != 200:
                return None
            dec = _aes_cbc_decrypt(key, base64.b64decode(resp["data"]))
            if dec is None:
                return None
            return json.loads(dec.decode("utf-8", "ignore"))
        except Exception:
            return None

    def _to_vod(self, row):
        vid = str(row.get("vodId", ""))
        if vid:
            self._cache[vid] = row
        name = row.get("vodName") or ""
        pic = _proxy_pic(row.get("vodPic") or "")
        hits = row.get("vodHits")
        remarks = ""
        if hits is not None:
            remarks = "%s人气" % hits
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
        }

    def _pagecount(self, data, pg, size):
        try:
            total = int(data.get("total") or 0)
        except Exception:
            total = 0
        rows = data.get("rows") or []
        if total > 1:
            return max(1, (total + size - 1) // size)
        # 分类接口 total 不可信(恒为 1): 满页则认为还有下一页
        return pg + 1 if len(rows) >= size else pg

    def _list(self, params, pg):
        params = dict(params)
        params["order"] = params.get("order", "desc")
        params["page"] = str(pg)
        params["size"] = str(PAGE_SIZE)
        # 注意: 不要发 count 参数, 发了它返回的 total 会恒为 1
        data = self._api("/vod/search.php", params)
        if not data:
            return {"list": [], "pagecount": pg}
        rows = data.get("rows") or []
        return {
            "list": [self._to_vod(r) for r in rows],
            "pagecount": self._pagecount(data, pg, PAGE_SIZE),
        }

    def homeContent(self, *args):
        classes = [{"type_id": tid, "type_name": name} for tid, name, _ in CATS]
        featured = []
        try:
            d = self._list({"by": "vod_time"}, 1)
            featured = d["list"][:12]
        except Exception:
            featured = []
        return {"class": classes, "list": featured}

    def homeVideoContent(self, *args):
        try:
            d = self._list({"by": "vod_time"}, 1)
            return {"list": d["list"][:12]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter=None, extend=None, *args):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        params = _CAT_MAP.get(str(tid))
        if params is None:
            params = {"by": "vod_time"}
        try:
            return self._list(params, pg)
        except Exception:
            return {"list": [], "pagecount": pg}

    def detailContent(self, ids, *args):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) else str(ids)
        row = self._cache.get(vid)
        info = None
        try:
            info = self._api("/vod/info.php", {"id": int(vid)}, timeout=20)
        except Exception:
            info = None
        if info is None and row is None:
            return {"list": []}
        name = ""
        pic = ""
        tag = ""
        hits = None
        code = ""
        play_url = ""
        vtime = ""
        if info:
            name = info.get("vodName") or ""
            pic = _proxy_pic(info.get("vodPic") or "")
            tag = info.get("vodTag") or ""
            hits = info.get("vodHits")
            code = info.get("code") or ""
            play_url = info.get("vodPlayUrl") or ""
            vtime = info.get("vodTime") or ""
        if row:
            name = name or row.get("vodName") or ""
            pic = pic or _proxy_pic(row.get("vodPic") or "")
            tag = tag or row.get("vodTag") or ""
            if hits is None:
                hits = row.get("vodHits")
            code = code or row.get("code") or ""
            play_url = play_url or row.get("vodPlayUrl") or ""
        # play key 用 code (32 位 hex): playerContent 可直接拼 m3u8, 不依赖缓存
        key = code if code else vid
        remarks = ""
        if hits is not None:
            remarks = "%s人气" % hits
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_content": tag,
            "vod_play_from": "爱豆",
            "vod_play_url": "正片$" + key,
        }
        if vtime:
            vod["vod_year"] = str(vtime)[:4]
        return {"list": [vod]}

    def searchContent(self, key, quick=None, pg="1", *args):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        try:
            return self._list({"wd": str(key)}, pg)
        except Exception:
            return {"list": [], "pagecount": pg}

    def playerContent(self, flag, id, vipFlags=None, *args):
        pid = str(id).strip()
        url = ""
        if len(pid) == 32 and all(c in "0123456789abcdef" for c in pid.lower()):
            url = BASE + "/api/m3u8/" + pid.lower() + ".m3u8"
        else:
            # 数字 vodId: 查详情拿播放地址
            try:
                info = self._api("/vod/info.php", {"id": int(pid)}, timeout=20)
                if info and info.get("vodPlayUrl"):
                    url = BASE + info["vodPlayUrl"]
                elif info and info.get("code"):
                    url = BASE + "/api/m3u8/" + info["code"] + ".m3u8"
            except Exception:
                url = ""
            if not url:
                row = self._cache.get(pid)
                if row and row.get("vodPlayUrl"):
                    url = BASE + row["vodPlayUrl"]
                elif row and row.get("code"):
                    url = BASE + "/api/m3u8/" + row["code"] + ".m3u8"
        if not url:
            return {"parse": 0, "playUrl": "", "url": ""}
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": UA, "Referer": BASE + "/"},
        }

    # ---- 兼容接口 ----
    def getName(self, *args):
        return "爱豆"

    def init(self, *args):
        return True

    def getDependence(self, *args):
        return ""

    def isVideoFormat(self, url, *args):
        u = str(url).lower()
        return any(u.endswith(e) for e in
                   (".m3u8", ".mp4", ".m4a", ".mp3", ".flac", ".aac",
                    ".wav", ".ogg", ".ts", ".flv", ".mkv", ".avi", ".mov"))

    def manualVideoCheck(self, *args):
        return True

    def localProxy(self, param, *args):
        return [200, "video/MP2T", None, ""]

    def proxy(self, param, *args):
        # 壳子走蜘蛛 proxy 取图时也反转字节, 回真图 + 正确 Content-Type
        try:
            url = param.get("url") if isinstance(param, dict) else None
            if not url:
                return {"code": 400, "msg": "no url"}
            if "/img?url=" in url or "ghjfg.shop" in url or url.lower().endswith(".ttf"):
                real = url
                if "/img?url=" in url:
                    real = _unquote(url.split("/img?url=", 1)[1].split("&")[0])
                raw = _fetch_pic_bytes(real)
                rev = _unreverse_pic(raw)
                if rev is not None:
                    raw = rev
                return {"code": 200, "content": raw,
                        "headers": {"Content-Type": _img_ct(raw, real)}}
            return {"code": 200, "content": b"",
                    "headers": {"Content-Type": "application/x-mpegURL"}}
        except Exception as e:
            return {"code": 500, "msg": str(e)}

    def destroy(self, *args):
        return True
