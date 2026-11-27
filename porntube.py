# -*- coding: utf-8 -*-
  
import re
import json
import base64
import hashlib
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    try:
        from spider import Spider as BaseSpider
    except Exception:
        class BaseSpider(object):
            pass


# ---------------- 纯 Python AES-256-CBC 解密（CryptoJS 口令模式） ----------------
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
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36, 0x6c, 0xd8, 0xab, 0x4d]


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


def _mul_table(n):
    return [_gmul(i, n) for i in range(256)]


_MUL9 = _mul_table(9)
_MUL11 = _mul_table(11)
_MUL13 = _mul_table(13)
_MUL14 = _mul_table(14)


def _expand_key(key):
    Nk, Nr = 8, 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(Nk)]
    for i in range(Nk, 4 * (Nr + 1)):
        t = list(w[i - 1])
        if i % Nk == 0:
            t = [_SBOX[t[1]] ^ _RCON[i // Nk - 1], _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]]
        elif Nk > 6 and i % Nk == 4:
            t = [_SBOX[x] for x in t]
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


def _aes256_decrypt_block(block, rkeys):
    s = [b ^ k for b, k in zip(block, rkeys[14])]
    for rnd in range(13, 0, -1):
        s = _inv_shift_rows(s)
        s = [_INV_SBOX[b] for b in s]
        s = [b ^ k for b, k in zip(s, rkeys[rnd])]
        s = _inv_mix_columns(s)
    s = _inv_shift_rows(s)
    s = [_INV_SBOX[b] for b in s]
    s = [b ^ k for b, k in zip(s, rkeys[0])]
    return bytes(s)


def _aes256_cbc_decrypt(key, iv, data):
    if len(data) % 16:
        raise ValueError("ciphertext not multiple of 16")
    rkeys = _expand_key(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        dec = _aes256_decrypt_block(blk, rkeys)
        out.extend(b ^ p for b, p in zip(dec, prev))
        prev = blk
    pad = out[-1] if out else 0
    if not 1 <= pad <= 16 or out[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad padding")
    return bytes(out[:-pad])


def _evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
    out = b""
    prev = b""
    pw = password.encode("utf-8") if isinstance(password, str) else password
    while len(out) < key_len + iv_len:
        d = hashlib.md5(prev + pw + salt).digest()
        prev = d
        out += d
    return out[:key_len], out[key_len:key_len + iv_len]


def _cryptojs_decrypt_json(b64cipher, passphrase="xxx"):
    """CryptoJS AES 口令密文 -> JSON 对象。"""
    raw = base64.b64decode(b64cipher)
    if raw[:8] != b"Salted__":
        raise ValueError("not a CryptoJS salted ciphertext")
    key, iv = _evp_bytes_to_key(passphrase, raw[8:16])
    plain = _aes256_cbc_decrypt(key, iv, raw[16:])
    return json.loads(plain.decode("utf-8"))


# ---------------- 源 ----------------
# 前端 ce.m.httpNames 的 7 个 + Surge 脚本 MITM 列表里的 tianmtv
_HOSTS = [
    "v2.cdn199.com",
    "v2.kekecdn.net",
    "v2.luchu.org",
    "v2.madou.ws",
    "v2.papapa.biz",
    "v2.tianmtv.com",
    "v2.xiaoshuo.info",
    "v2.xiaoshuo.la",
]
_CATS = [
    ("hot", "当前热播"),
    ("recent", "最新上传"),
    ("vip", "VIP专区"),
    ("japan", "无码高清"),
    ("high", "站长推荐"),
]
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class Spider(BaseSpider):
    def getName(self):
        return "PornTube"

    def init(self, extend=""):
        pass

    def __init__(self):
        super(Spider, self).__init__()
        self._host_ok = None
        self.headers = {
            "User-Agent": _UA,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Origin": "https://porntube.cool",
            "Referer": "https://porntube.cool/",
        }

    # ---------- 底层 ----------
    def _post_host(self, host, route, params):
        body = {
            "app": "porntube.cool",
            "isStandalone": False,
            "theLink": "novaluenull",
            "uuid": "novalue",
            "url": route,
            "version": "260901",
            "deviceInfo": {},
        }
        if params:
            body.update(params)
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "https://%s/js" % host, data=data, headers=self.headers,
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        obj = json.loads(raw.decode("utf-8", "ignore"))
        if isinstance(obj, dict) and "r" in obj:
            return _cryptojs_decrypt_json(obj["r"])
        return obj

    def _api(self, route, params=None):
        """8 host 轮换：先试上次可用的，失败再全量轮询。"""
        hosts = list(_HOSTS)
        if self._host_ok and self._host_ok in hosts:
            hosts.remove(self._host_ok)
            hosts.insert(0, self._host_ok)
        last_err = None
        for host in hosts:
            try:
                data = self._post_host(host, route, params)
                self._host_ok = host
                return data
            except Exception as e:
                last_err = e
                continue
        return None

    @staticmethod
    def _as_list(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("list", "data", "videos", "items"):
                if isinstance(data.get(k), list):
                    return data[k]
        return []

    @staticmethod
    def _vod(v):
        if not isinstance(v, dict):
            return None
        vid = v.get("id") or v.get("_id") or v.get("vId") or ""
        if not vid:
            return None
        title = v.get("title") or v.get("title_en") or ""
        thumbs = v.get("thumbnails") or []
        pic = thumbs[0] if isinstance(thumbs, list) and thumbs else ""
        year = ""
        ct = v.get("createdTime") or ""
        if isinstance(ct, str) and len(ct) >= 4 and ct[:4].isdigit():
            year = ct[:4]
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": v.get("durationStr") or "",
            "vod_year": year,
        }

    def _list(self, type_id, pg):
        data = self._api("/sevenVideos?page=%s&type=%s" % (pg, type_id))
        items = []
        for v in self._as_list(data):
            vod = self._vod(v)
            if vod:
                items.append(vod)
        return items

    # ---------- T4 接口 ----------
    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in _CATS]
        result = {"class": classes, "filters": {}}
        try:
            lst = self._list("hot", 1)
            if lst:
                result["list"] = lst
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            lst = self._list("hot", 1)
        except Exception:
            lst = []
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        lst = self._list(tid, pg)
        return {
            "page": pg,
            "pagecount": 9999 if lst else pg,
            "limit": 20,
            "total": 9999 if lst else 0,
            "list": lst,
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ""
        if not vid:
            return {"list": []}
        d = self._api("/sevenVideos/" + vid, {"url_search": ""})
        if not isinstance(d, dict):
            return {"list": []}
        thumbs = d.get("thumbnails") or []
        pic = thumbs[0] if isinstance(thumbs, list) and thumbs else ""
        year = ""
        ct = d.get("createdTime") or ""
        if isinstance(ct, str) and len(ct) >= 4 and ct[:4].isdigit():
            year = ct[:4]
        m3u8s = d.get("m3u8s") or []
        if not m3u8s and d.get("m3u8"):
            m3u8s = [d["m3u8"]]
        m3u8s = [u for u in m3u8s if isinstance(u, str) and u.startswith("http")]
        if m3u8s:
            play_from = "$$$".join("线路%d" % (i + 1) for i in range(len(m3u8s)))
            play_url = "$$$".join("正片$%s" % u for u in m3u8s)
        else:
            play_from = ""
            play_url = ""
        tags = d.get("tags") or d.get("tags_en") or ""
        vod = {
            "vod_id": vid,
            "vod_name": d.get("title") or d.get("title_en") or "",
            "vod_pic": pic,
            "vod_year": year,
            "vod_director": d.get("user") or d.get("user_en") or "",
            "vod_remarks": d.get("durationStr") or "",
            "vod_content": tags,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = str(id)
        if "$" in url:
            url = url.rsplit("$", 1)[-1]
        header = {
            "User-Agent": _UA,
            "Referer": "https://porntube.cool/",
            "Origin": "https://porntube.cool",
        }
        return {"parse": 0, "playUrl": "", "url": url, "header": header}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        params = {
            "page": pg,
            "keywords": key,
            "filterCategory": "all",
            "filterTimeInDays": "all",
            "filterViews": "all",
            "filterDurationInMins": "all",
            "sortBy": "time",
            "keywordLogic": "or",
        }
        data = self._api("/searchSevenVideos", params)
        lst = []
        for v in self._as_list(data):
            vod = self._vod(v)
            if vod:
                lst.append(vod)
        return {
            "page": pg,
            "pagecount": 9999 if lst else pg,
            "limit": 20,
            "total": 9999 if lst else 0,
            "list": lst,
        }
