# -*- coding: utf-8 -*-
# 有料视频 (yliao)
#
# 站：有料视频 H5 网页版（入口 fbslur.tazitev.cn 是分享落地域名，备用域
# uliao.me | ylgo.me | yliao.me）。Vue SPA，Hash 路由。
#
# 绕法是 B2（2026-11-26 实站验证）：游客调详情接口拿到的是 60 秒试看
# m3u8（index2.m3u8），但同一目录下的 index.m3u8 就是完整全片，游客裸拉
# 200，标准 AES-128，播放器直接播，不需要账号、VIP、localProxy、Worker。
# 墙只拦 API 给的地址，不管 index.m3u8 本身；前端标志位不用改。
#
# 协议（JS：assets/index-BwH6VZq2.js）：
#   初始化：POST {init_host}/player/do_init_h5，体
#       {system:3, mobile_model, system_version, new_live:1}，
#       自动发游客账号（每次 mint 新 uid + 64 位 hex token）。
#       init host 轮询：wyinit.al.ndsgnw.com/api、init.ylapi2028.com/api、
#       wyinit.al.akqgmf.com/api、wyinit.ylapi9527.com/api。
#       响应 data 含 api_url（路径为空时补 /api）、api_backup、pay_url。
#   请求签名：头带 time（Unix 秒）、sign、X-App-Version: 12，
#       登录后另带 uid、Access-Token。
#       sign = md5(<pathname>?time=<t>&a2ef62227536ab01) 小写，
#       pathname 是 baseURL+path 解析后的完整路径，必须含 /api 前缀
#       （用 /player/do_init_h5 算签会回 code 4 签名验证错误）。
#       Content-Type: application/x-www-form-urlencoded。
#   响应加密：响应体是 base64 文本，AES-128-CBC 解密，
#       key = ec5279154d05ac2c、IV = 515cd1587d7cfbdd（均为 16 字符 ASCII
#       当 UTF-8，出自公开 JS bundle），纯 Python 实现。
#       解出 {"code":1,"msg":"success","data":...}；code 3 = 鉴权失败。
#
# 接口（全部游客态实测通过）：
#   POST /video/index               {}                        13 分类 + 推荐
#   POST /video/cate_list           {cate_id, page}           分类（二级分组
#       嵌套 list，p1 约 42 条；cate2_list 的字段名与 list 组里不同，
#       组名以 list 组里的 cate2_name 为准）
#   POST /video/video_library_list  {cate_id, page}           不认 cate_id，
#       传任何分类都返回同一批最新 20 条——分类千万别用它
#   POST /video/new_update_list     {page}                    p1 20 条，p2 为空
#   POST /video/search_list         {keyword, page}           搜“调教”10 条
#   POST /video/video_info          {video_id, is_h5:1, system:3}
#       video_info.url = .../index2.m3u8（试看），封面 img 直链。
#       字段：can_play:0、lock_type:1、is_buy:0、coin:0、video_type:1、
#       episode_count:0。
#   m3u8 自身：#EXT-X-KEY:METHOD=AES-128,URI="key.key"，IV 有的写在 KEY 行
#       里，有的缺省；key.key 16 字节同目录裸拉；播放器按标准 HLS 处理，
#       无需 localProxy 改写。
#   封面：img 字段的 cover.jpg 拉下来是 base64 文本，里层是“盐字节 +
#       逐字节混淆”密文（前端 wh 函数），须按“封面 cover.jpg 解密”还原
#       成图片再拼 data URI 当 vod_pic，直链盒子显示不出；解出的图有
#       JPEG 也有 WebP，mime 按魔数定；解失败回退原直链。
#       cloudfront 的 .gif 是广告图（真 GIF），源里不用广告列表，无需处理。
#
# 坑：
#   1. 选集分隔符用单个 $（$$ 会被壳子切出空地址）。
#   2. 播放地址现取现播，不缓存（每次调 video_info 现拿现换）。
#   3. token 有效期未验证：每次 init 都发新 uid；code 3 时源内自动重取
#      一次再试。
#   4. 剧集类视频（episode_count>0）的 /video/episode_list 结构未验证，
#      源内防御性解析，拿不到分集时回退到单集。
#   5. coin>0 的单买视频是否同样裸出全片未验证；new_update_list p2 为空
#      的原因未明；m3u8/CDN 域名是否轮换未验证（本次均为 qgsp.m.cptvjs.cn）。
#   6. 封面 cover.jpg 是加密的 base64 文本（见“封面 cover.jpg 解密”），
#      须解码后拼 data URI；cloudfront 的 .gif 是广告图，真 GIF，源里
#      不用广告列表，无需处理。
#   7. /video/video_library_list 不认 cate_id（2026-11-26 实站证实：
#      传 348、44、38 返回的全是同一批最新 20 条，首 3 条都是
#      74050/74028/73990，20/20 重叠），分类必须走 /video/cate_list，
#      它返回二级分组嵌套 list（p1 6 组约 42 条，p2 剩余组），嵌套视频
#      字段是 video_id/video_title/video_img/video_is_vip（不是
#      id/title/img/is_vip）。

import base64
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    try:
        from base.spider import BaseSpider
    except ImportError:
        try:
            from spider import Spider as BaseSpider
        except ImportError:
            try:
                from spider import BaseSpider
            except ImportError:
                class BaseSpider:
                    pass


# ---------------- 纯 Python AES-128-CBC 解密（标准库 only） ----------------
_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36, 0x6c, 0xd8, 0xab, 0x4d]
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


_MUL9 = [_gmul(i, 9) for i in range(256)]
_MUL11 = [_gmul(i, 11) for i in range(256)]
_MUL13 = [_gmul(i, 13) for i in range(256)]
_MUL14 = [_gmul(i, 14) for i in range(256)]


def _expand_key128(key):
    Nk, Nr = 4, 10
    w = [list(key[4 * i:4 * i + 4]) for i in range(Nk)]
    for i in range(Nk, 4 * (Nr + 1)):
        t = list(w[i - 1])
        if i % Nk == 0:
            t = [_SBOX[t[1]] ^ _RCON[i // Nk - 1], _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]]
        w.append([w[i - Nk][j] ^ t[j] for j in range(4)])
    return [bytes(sum(w[4 * r:4 * r + 4], [])) for r in range(Nr + 1)]


def _inv_shift_rows(s):
    out = [0] * 16
    for r in range(4):
        for c in range(4):
            out[4 * c + r] = s[4 * ((c - r) % 4) + r]
    return out


def _inv_mix_columns(s):
    out = [0] * 16
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c:4 * c + 4]
        out[4 * c + 0] = _MUL14[a0] ^ _MUL11[a1] ^ _MUL13[a2] ^ _MUL9[a3]
        out[4 * c + 1] = _MUL9[a0] ^ _MUL14[a1] ^ _MUL11[a2] ^ _MUL13[a3]
        out[4 * c + 2] = _MUL13[a0] ^ _MUL9[a1] ^ _MUL14[a2] ^ _MUL11[a3]
        out[4 * c + 3] = _MUL11[a0] ^ _MUL13[a1] ^ _MUL9[a2] ^ _MUL14[a3]
    return out


def _aes128_decrypt_block(block, rkeys):
    s = [b ^ k for b, k in zip(block, rkeys[10])]
    for rnd in range(9, 0, -1):
        s = [_INV_SBOX[b] for b in s]
        s = _inv_shift_rows(s)
        s = [b ^ k for b, k in zip(s, rkeys[rnd])]
        s = _inv_mix_columns(s)
    s = [_INV_SBOX[b] for b in s]
    s = _inv_shift_rows(s)
    s = [b ^ k for b, k in zip(s, rkeys[0])]
    return bytes(s)


_AES_KEY = b"ec5279154d05ac2c"
_AES_IV = b"515cd1587d7cfbdd"
_AES_RKEYS = None


def _aes_cbc_decrypt(b64text):
    """响应体 base64 文本 → AES-128-CBC 解密 → 明文字节（含 PKCS7 去填充）。"""
    global _AES_RKEYS
    if _AES_RKEYS is None:
        _AES_RKEYS = _expand_key128(_AES_KEY)
    if isinstance(b64text, bytes):
        b64text = b64text.decode("ascii", "ignore")
    b64text = "".join(b64text.split())
    try:
        raw = base64.b64decode(b64text)
    except Exception:
        return b""
    if not raw or len(raw) % 16:
        return b""
    out = bytearray()
    prev = _AES_IV
    for i in range(0, len(raw), 16):
        blk = raw[i:i + 16]
        dec = _aes128_decrypt_block(blk, _AES_RKEYS)
        out.extend(bytes(a ^ b for a, b in zip(dec, prev)))
        prev = blk
    if out:
        pad = out[-1]
        if 1 <= pad <= 16 and len(out) >= pad:
            out = out[:-pad]
    return bytes(out)


# ---------------- 封面 cover.jpg 解密（前端 AppImage 同款） ----------------
# cover.jpg 拉下来是 base64 文本，里层是“盐字节 + 逐字节混淆”的密文，
# 前端（index.js 的 wh 函数）先 base64 解码，再按下面算法还原。
# 密钥流 = SHA256("sdkvgl2hj92h23h923h") 的 32 字节；第 1 字节是盐 n；
# 还原：out[i] = ((密文[i] - n) ^ 密钥流[i % 32]) & 0xff（JS 里先减后异或）。
# mime 按魔数定（前端 Mh 同款）：FFD8→jpeg、89504E47→png、GIF→gif、
# 第 8-11 字节 WEBP→webp、BM→bmp，默认 jpeg。
# 实站验证（2026-11-26）：3 个真实 cover.jpg 全解出有效图片（PIL 通过），
# 其中 2 个是 WebP（800×448/449）、1 个是 JPEG（1928×1080）。
_COVER_KEY = hashlib.sha256(b"sdkvgl2hj92h23h923h").digest()
_COVER_MAX_BYTES = 6000000


def _cover_sniff(data):
    if len(data) >= 2 and data[0] == 0xFF and data[1] == 0xD8:
        return "image/jpeg"
    if len(data) >= 4 and data[:4] == b"\x89PNG":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"GIF":
        return "image/gif"
    if len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 2 and data[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


def _cover_decrypt(text):
    """cover.jpg 的 base64 文本 → 解密后的图片字节；失败返回 b""。"""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except Exception:
            return b""
    b64 = "".join(text.split())
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return b""
    if len(raw) < 2:
        return b""
    n = raw[0]
    body = raw[1:]
    return bytes(((b - n) ^ _COVER_KEY[i % 32]) & 0xFF
                 for i, b in enumerate(body))


class Spider(BaseSpider):
    SITE_NAME = "有料视频"
    HOST = "https://fbslur.tazitev.cn"
    REFERER = "https://fbslur.tazitev.cn/"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    TIMEOUT = 15
    PER_PAGE = 20
    SALT = "a2ef62227536ab01"
    # init host 列表（轮询；base 自带 /api 后缀）
    INIT_HOSTS = [
        "https://wyinit.al.ndsgnw.com/api",
        "https://init.ylapi2028.com/api",
        "https://wyinit.al.akqgmf.com/api",
        "https://wyinit.ylapi9527.com/api",
    ]
    # /video/index 挂了时的兜底分类（2026-11-26 实站核对）
    FALLBACK_CATS = [
        ("348", "17岁"),
        ("44", "乱伦禁忌"),
        ("320", "热点爆料"),
        ("359", "SM调教"),
        ("38", "国产精选"),
        ("48", "极致稀缺"),
        ("41", "福利博主"),
        ("37", "成人厂牌"),
        ("39", "日韩AV"),
        ("40", "欧美性爱"),
        ("262", "性爱课堂"),
        ("43", "二次元"),
        ("42", "三级片"),
    ]

    def getName(self):
        return self.SITE_NAME

    def init(self, extend=""):
        self.extend = extend or ""
        self._api_base = ""
        self._token = ""
        self._uid = ""
        self._index_cache = None
        self._inited = False
        self._cover_cache = {}

    def __init__(self):
        self.extend = ""
        self._api_base = ""
        self._token = ""
        self._uid = ""
        self._index_cache = None
        self._inited = False
        self._cover_cache = {}

    # ── 基础请求 ──────────────────────────────────────────
    def _http_post(self, url, data, headers):
        last = b""
        for _ in range(2):
            try:
                req = urllib.request.Request(url, data=data, headers=headers,
                                             method="POST")
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return resp.read()
            except urllib.error.HTTPError:
                return b""
            except Exception:
                time.sleep(0.5)
        return last

    # ── 封面：cover.jpg 取回 → 解密 → data URI ──────────────────
    def _http_get(self, url):
        """拉封面等 GET 资源；失败返回 b""。"""
        h = {"User-Agent": self.UA, "Referer": self.REFERER}
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers=h, method="GET")
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return resp.read()
            except Exception:
                time.sleep(0.3)
        return b""

    def _decode_cover(self, url):
        """单个封面 URL → data URI；已是真图或解失败时返回原 URL。"""
        if not url or not url.startswith("http"):
            return url or ""
        cached = self._cover_cache.get(url)
        if cached is not None:
            return cached
        result = url
        try:
            raw = self._http_get(url)
            if raw and len(raw) <= _COVER_MAX_BYTES:
                is_image = (
                    (len(raw) >= 2 and raw[:2] == b"\xff\xd8")
                    or (len(raw) >= 4 and raw[:4] == b"\x89PNG")
                    or (len(raw) >= 3 and raw[:3] == b"GIF")
                    or (len(raw) >= 2 and raw[:2] == b"BM")
                    or (len(raw) >= 12 and raw[:4] == b"RIFF"
                        and raw[8:12] == b"WEBP"))
                if not is_image:
                    dec = _cover_decrypt(raw)
                    if dec and len(dec) >= 12:
                        mime = _cover_sniff(dec)
                        result = ("data:%s;base64,%s" % (
                            mime, base64.b64encode(dec).decode("ascii")))
        except Exception:
            result = url
        self._cover_cache[url] = result
        return result

    def _fill_covers(self, items):
        """并行把一批 vod 项的封面解成 data URI；失败项保留原直链。"""
        todo = [it for it in items
                if it.get("vod_pic", "").startswith("http")]
        if not todo:
            return items
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(self._decode_cover,
                                  [it["vod_pic"] for it in todo]))
        for it, uri in zip(todo, results):
            it["vod_pic"] = uri
        return items

    def _post(self, url, body, token=None, uid=None):
        t = int(time.time())
        pathname = urllib.parse.urlparse(url).path
        sign = hashlib.md5(("%s?time=%d&%s" % (pathname, t, self.SALT)
                            ).encode("utf-8")).hexdigest()
        data = urllib.parse.urlencode(body or {}).encode("utf-8")
        h = {"User-Agent": self.UA, "Referer": self.REFERER,
             "Content-Type": "application/x-www-form-urlencoded",
             "X-App-Version": "12", "time": str(t), "sign": sign}
        if token:
            h["Access-Token"] = token
        if uid:
            h["uid"] = str(uid)
        return self._http_post(url, data, h)

    @staticmethod
    def _parse_resp(raw):
        """响应可能是明文 JSON，也可能是 AES 加密的 base64 文本。"""
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            pass
        dec = _aes_cbc_decrypt(raw)
        if not dec:
            return None
        try:
            return json.loads(dec.decode("utf-8", "ignore"))
        except Exception:
            return None

    # ── 游客初始化（懒调，init 内零网络） ───────────────────
    def _do_init(self):
        body = {"system": "3", "mobile_model": "unknown",
                "system_version": "unknown", "new_live": "1"}
        for host in self.INIT_HOSTS:
            url = host.rstrip("/") + "/player/do_init_h5"
            env = self._parse_resp(self._post(url, body))
            if env and env.get("code") == 1 and isinstance(env.get("data"), dict):
                d = env["data"]
                api = (d.get("api_url") or "").rstrip("/")
                if not api:
                    continue
                if urllib.parse.urlparse(api).path in ("", "/"):
                    api = api + "/api"
                self._api_base = api
                pi = d.get("player_info") or {}
                self._token = str(pi.get("token") or "")
                self._uid = str(pi.get("uid") or "")
                self._inited = True
                return True
        return False

    def _ensure_init(self):
        if self._inited and self._api_base:
            return True
        return self._do_init()

    def _call(self, path, body=None, retry_auth=True):
        """调运行时 API，成功返回 data；失败返回 None。
        code 3（鉴权失败）时重取一次游客 token 再试一次。"""
        if not self._ensure_init():
            return None
        url = self._api_base.rstrip("/") + "/" + path.lstrip("/")
        env = self._parse_resp(self._post(url, body or {},
                                          self._token, self._uid))
        if env and env.get("code") == 3 and retry_auth:
            self._inited = False
            self._api_base = ""
            self._token = ""
            self._uid = ""
            if self._ensure_init():
                url = self._api_base.rstrip("/") + "/" + path.lstrip("/")
                env = self._parse_resp(self._post(url, body or {},
                                                  self._token, self._uid))
        if env and env.get("code") == 1:
            return env.get("data")
        return None

    # ── 分类 / 首页 ───────────────────────────────────────
    def _index(self):
        if self._index_cache is not None:
            return self._index_cache
        d = self._call("/video/index", {})
        if isinstance(d, dict):
            self._index_cache = d
            return d
        return {}

    def _cats(self):
        d = self._index()
        cats = []
        for c in d.get("cate_list") or []:
            cid = c.get("cate_id")
            name = (c.get("name") or "").strip()
            if cid is not None and name:
                cats.append((str(cid), name))
        if not cats:
            cats = list(self.FALLBACK_CATS)
        return cats

    def homeContent(self, filter):
        cats = [("0", "最新更新")] + self._cats()
        return {"class": [{"type_id": i, "type_name": n} for i, n in cats],
                "filters": {}}

    def homeVideoContent(self):
        d = self._index()
        items = []
        for g in d.get("recommend_list") or []:
            items = g.get("list") or []
            if items:
                break
        if not items:
            items = d.get("day_recommend") or []
        items = [v for v in (self._vod(x)
                             for x in items[:self.PER_PAGE]) if v]
        return {"list": self._fill_covers(items)}

    # ── 列表 ──────────────────────────────────────────────
    @staticmethod
    def _vod(x):
        if not isinstance(x, dict):
            return None
        vid = x.get("video_id") or x.get("id")
        if vid is None:
            return None
        title = (x.get("title") or "").strip()
        if not title:
            return None
        remarks = (x.get("video_time") or "").strip()
        if x.get("is_vip"):
            remarks = (remarks + " · VIP") if remarks else "VIP"
        try:
            coin = int(x.get("coin") or 0)
        except Exception:
            coin = 0
        if coin > 0:
            remarks = (remarks + " · 金币%d" % coin) if remarks \
                else "金币%d" % coin
        return {"vod_id": str(vid),
                "vod_name": title,
                "vod_pic": x.get("img") or "",
                "vod_remarks": remarks,
                "vod_actor": "",
                "vod_content": ""}

    @staticmethod
    def _vod_cate(x, group_name):
        """cate_list 嵌套视频映射：字段名与 video_library_list 不同
        （video_id/video_title/video_img/video_is_vip），
        vod_remarks 里带二级分组名（如“高中生”）方便区分。"""
        if not isinstance(x, dict):
            return None
        vid = x.get("video_id")
        if vid is None:
            return None
        title = (x.get("video_title") or "").strip()
        if not title:
            return None
        remarks = (x.get("video_time") or "").strip()
        if group_name:
            remarks = (remarks + " · " + group_name) if remarks \
                else group_name
        if x.get("video_is_vip"):
            remarks = (remarks + " · VIP") if remarks else "VIP"
        try:
            coin = int(x.get("coin") or 0)
        except Exception:
            coin = 0
        if coin > 0:
            remarks = (remarks + " · 金币%d" % coin) if remarks \
                else "金币%d" % coin
        return {"vod_id": str(vid),
                "vod_name": title,
                "vod_pic": x.get("video_img") or "",
                "vod_remarks": remarks,
                "vod_actor": "",
                "vod_content": ""}

    def _cate_items(self, data):
        """cate_list 返回：{cate2_list, list: [{cate2_id, cate2_name,
        cate2_title, list: [视频...]}]}，把各组嵌套 list 拍平成一页。"""
        items = []
        if not isinstance(data, dict):
            return items
        for g in data.get("list") or []:
            if not isinstance(g, dict):
                continue
            gname = (g.get("cate2_name") or "").strip()
            for x in g.get("list") or []:
                v = self._vod_cate(x, gname)
                if v:
                    items.append(v)
        return items

    @staticmethod
    def _page(data):
        if isinstance(data, dict):
            items = data.get("list") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return items

    def _page_items(self, data):
        return [v for v in (self._vod(x) for x in self._page(data)) if v]

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid or "0")
        if tid == "0":
            data = self._call("/video/new_update_list", {"page": pg})
            items = self._fill_covers(self._page_items(data))
        else:
            # video_library_list 不认 cate_id（传任何分类都返回同一批
            # 最新 20 条），分类必须走 /video/cate_list（二级分组嵌套）。
            try:
                cid = int(tid)
            except Exception:
                cid = tid
            data = self._call("/video/cate_list",
                              {"cate_id": cid, "page": pg})
            items = self._fill_covers(self._cate_items(data))
        pagecount = pg if len(items) < self.PER_PAGE else pg + 1
        return {"page": pg, "pagecount": pagecount,
                "limit": self.PER_PAGE, "total": 0, "list": items}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        data = self._call("/video/search_list",
                          {"keyword": key or "", "page": pg})
        items = self._fill_covers(self._page_items(data))
        pagecount = pg if len(items) < self.PER_PAGE else pg + 1
        return {"page": pg, "pagecount": pagecount,
                "limit": self.PER_PAGE, "total": 0, "list": items}

    # ── 详情 ──────────────────────────────────────────────
    def _video_info(self, vid):
        d = self._call("/video/video_info",
                       {"video_id": vid, "is_h5": 1, "system": 3})
        if isinstance(d, dict):
            return d.get("video_info") or {}
        return {}

    def _episodes(self, vid):
        """剧集类：/video/episode_list 结构未验证，防御性解析；
        拿不到分集时返回空，调用方回退到单集。"""
        d = self._call("/video/episode_list", {"video_id": vid})
        items = []
        if isinstance(d, dict):
            items = d.get("list") or d.get("episodes") or []
        elif isinstance(d, list):
            items = d
        eps = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            url = it.get("url") or ""
            name = it.get("title") or it.get("name") or ("第%d集" % (i + 1))
            if url:
                eps.append("%s$playurl@@%s" % (
                    name, urllib.parse.quote(url, safe="")))
            else:
                eps.append("%s$playep@@%s@@%d" % (name, vid, i + 1))
        return eps

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0]) if ids else ""
        else:
            raw = str(ids or "").split(",")[0].strip()
        vid = raw.split("@@")[0].strip()
        if not vid:
            return {"list": []}
        vi = self._video_info(vid)
        if not vi:
            return {"list": []}
        title = (vi.get("title") or "").strip() or vid
        pic = vi.get("img") or ""
        remarks = (vi.get("video_time") or "").strip()
        if vi.get("is_vip"):
            remarks = (remarks + " · VIP") if remarks else "VIP"
        try:
            coin = int(vi.get("coin") or 0)
        except Exception:
            coin = 0
        if coin > 0:
            remarks = (remarks + " · 金币%d" % coin) if remarks \
                else "金币%d" % coin
        try:
            ep_count = int(vi.get("episode_count") or 0)
        except Exception:
            ep_count = 0
        eps = self._episodes(vid) if ep_count > 0 else []
        if not eps:
            eps = ["第1集$play@@%s" % vid]
        content = (vi.get("tags") or "")[:300]
        item = {"vod_id": str(vid), "vod_name": title,
                "vod_pic": pic, "vod_remarks": remarks,
                "vod_actor": "",
                "vod_content": content,
                "vod_play_from": "有料视频",
                "vod_play_url": "#".join(eps)}
        return {"list": self._fill_covers([item])}

    # ── 播放：index2（试看）→ index（全片）直出 ─────────────
    @staticmethod
    def _full_url(url):
        if not url:
            return ""
        if "index2.m3u8" in url:
            return url.replace("index2.m3u8", "index.m3u8")
        if "index1.m3u8" in url:
            return url.replace("index1.m3u8", "index.m3u8")
        return url

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "")
        url = ""
        m = re.match(r"play@@(\d+)", raw)
        if m:
            vi = self._video_info(m.group(1))
            url = vi.get("url") or ""
        elif raw.startswith("playurl@@"):
            url = urllib.parse.unquote(raw[len("playurl@@"):])
        elif raw.startswith("playep@@"):
            parts = raw.split("@@")
            if len(parts) == 3:
                try:
                    n = int(parts[2])
                except Exception:
                    n = 1
                d = self._call("/video/episode_list",
                               {"video_id": parts[1]})
                items = []
                if isinstance(d, dict):
                    items = d.get("list") or d.get("episodes") or []
                elif isinstance(d, list):
                    items = d
                if 1 <= n <= len(items) and isinstance(items[n - 1], dict):
                    url = items[n - 1].get("url") or ""
                if not url:
                    vi = self._video_info(parts[1])
                    url = vi.get("url") or ""
        full = self._full_url(url)
        if not full.startswith("http"):
            return {"parse": 0, "url": ""}
        return {"parse": 0, "url": full,
                "header": {"User-Agent": self.UA, "Referer": self.REFERER}}

    # ── localProxy：本源直出，不走代理 ─────────────────────
    def localProxy(self, param):
        return [404, "text/plain", b""]
