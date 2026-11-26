# coding=utf-8
# Jasna-LTX 资源库 https://ltxlib.dpdns.org/
# 按番号、标题、女优、片商、分类检索作品，查看封面、评分与截图。
# 实测（2026-11-25，手机浏览器 + 用户自己的代理网络）：
#   全部 4495 部（已确认 3627 / 待确认 868），默认按评分高到低；
#   前 3 部：IPX-811（田中レモン）、IPX-697（相沢みなみ）、ABW-087（涼森れむ）；
#   详情没有独立页面，卡片本身就是详情：番号 / 标题 / 女优 / 片商 /
#   日期 / 评分 / ed2k 或 magnet 链接（每部只有 1 条下载链接）/
#   中文字幕（subtitlecat，多为机翻）/ javdb 外链。
#   全库：ed2k 4223 部、磁力 272 部、字幕 3905 部。
#
# v2（2026-11-26）：分类按站点的筛选口径（状态 / 排序 / 链接类型 /
#   字幕 / 片商）；新增“女优”和“厂牌”两个动态列表——点开时从接口
#   实时扫全库，按作品数排，封面取该女优/厂牌的第一部作品，站点
#   上新后列表跟着变，不写死名单；女优/厂牌点开是她的作品列表。
#
# 这个站的接口不是明文 JSON，而是加密的：
#   1. 先过 Cloudflare Turnstile 人机验证（/api/verify），验证通过后
#      服务器才给安全会话；
#   2. 再用 ECDH P-256 + HKDF-SHA256 协商一把 AES-256-GCM 的密钥，
#      每次请求带 X-LTX-Session / X-LTX-Request，返回
#      application/vnd.ltx.encrypted+json 密文。
#   下面这份代码把第 2 步完整做出来了，只用 Python 标准库，不依赖
#   cryptography / requests，FongMi 的 py 环境里能直接跑。
#   第 1 步 py 做不了：Turnstile 只能在浏览器里过，py 没有浏览器。
#   所以没有验证票据时，列表会返回空 + 下面的 VERIFY_MSG，告诉你
#   需要先在浏览器里过验证，再把票据传进来。
#
# 票据怎么传（和 8se18.py 同一套做法，票据不要写进公开文件）：
#   在 FongMi 这个站的 ext 里传，例如
#   {"cookie": "验证后浏览器里的 Cookie（只填这一处）"}
#   或者 {"tickets": {"ltxlib.dpdns.org": {"cookie": "...", "ua": "..."}}}
#   也可以只传一串 Cookie 文本。COOKIE 留空，文件里永远不存真实票据。
#   票据和获取它的网络绑定，换网络要重新获取；过期了也要重新获取。

import base64
import gzip
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

BASE = "https://ltxlib.dpdns.org"
HOST = "ltxlib.dpdns.org"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
COOKIE = ""
PAGE_SIZE = 60
SCAN_LIMIT = 500  # 女优/厂牌扫库时每页拉取数；接口若有上限会自动按实际返回数分页

VERIFY_MSG = (
    "ltxlib.dpdns.org 需要先过 Cloudflare Turnstile 人机验证才能拉数据，"
    "py 自己过不了验证。请先在手机浏览器里打开 https://ltxlib.dpdns.org/ "
    "过验证、看到列表后，再把验证后浏览器里的 Cookie 通过这个站的 ext 传进来，"
    "例如 {\"cookie\": \"...\"}；票据和网络绑定，换网络 / 过期要重新获取。"
)
BLOCK_MSG = "ltxlib.dpdns.org 被 Cloudflare 拦截，请稍后再试，或按上面的方法传验证票据。"


class _VerifyNeeded(Exception):
    pass


class _Blocked(Exception):
    pass


# ---------------------------------------------------------------- b64url
def _b64u_encode(raw):
    return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")


def _b64u_decode(text):
    text = str(text or "").strip()
    if not text:
        return b""
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


# ---------------------------------------------------------------- AES
# S 盒用 GF(2^8) 现算，避免手抄 256 个常量抄错。
def _gf_mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return r & 0xFF


def _gf_pow(a, e):
    r = 1
    while e:
        if e & 1:
            r = _gf_mul(r, a)
        a = _gf_mul(a, a)
        e >>= 1
    return r


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _make_sbox():
    sbox = []
    for i in range(256):
        inv = 0 if i == 0 else _gf_pow(i, 254)
        s = inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2) ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63
        sbox.append(s & 0xFF)
    return sbox


_SBOX = _make_sbox()
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D]


def _aes_key_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = [_SBOX[temp[1]] ^ _RCON[i // nk - 1], _SBOX[temp[2]],
                    _SBOX[temp[3]], _SBOX[temp[0]]]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr


def _aes_encrypt_block(key, block):
    w, nr = _aes_key_expand(key)
    s = [[block[4 * c + r] for c in range(4)] for r in range(4)]

    def add_rk(rnd):
        for c in range(4):
            for r in range(4):
                s[r][c] ^= w[rnd * 4 + c][r]

    def sub_bytes():
        for r in range(4):
            for c in range(4):
                s[r][c] = _SBOX[s[r][c]]

    def shift_rows():
        for r in range(4):
            s[r] = s[r][r:] + s[r][:r]

    def mix_columns():
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _gf_mul(a[0], 2) ^ _gf_mul(a[1], 3) ^ a[2] ^ a[3]
            s[1][c] = a[0] ^ _gf_mul(a[1], 2) ^ _gf_mul(a[2], 3) ^ a[3]
            s[2][c] = a[0] ^ a[1] ^ _gf_mul(a[2], 2) ^ _gf_mul(a[3], 3)
            s[3][c] = _gf_mul(a[0], 3) ^ a[1] ^ a[2] ^ _gf_mul(a[3], 2)

    add_rk(0)
    for rnd in range(1, nr):
        sub_bytes()
        shift_rows()
        mix_columns()
        add_rk(rnd)
    sub_bytes()
    shift_rows()
    add_rk(nr)
    return bytes(s[r][c] for c in range(4) for r in range(4))


# ---------------------------------------------------------------- GHASH / GCM
def _gf128_mul(x, y):
    z = 0
    v = y
    for i in range(128):
        if (x >> (127 - i)) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ 0xE1000000000000000000000000000000
        else:
            v >>= 1
    return z


def _ghash(h, aad, ciphertext):
    h_int = int.from_bytes(h, "big")
    data = aad + b"\x00" * ((-len(aad)) % 16)
    data += ciphertext + b"\x00" * ((-len(ciphertext)) % 16)
    data += (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    y = 0
    for i in range(0, len(data), 16):
        y = _gf128_mul(y ^ int.from_bytes(data[i:i + 16], "big"), h_int)
    return y


def _aes_gcm_decrypt(key, iv, ciphertext_with_tag, aad):
    if len(ciphertext_with_tag) < 16:
        raise ValueError("ciphertext too short")
    ct, tag = ciphertext_with_tag[:-16], ciphertext_with_tag[-16:]
    h = _aes_encrypt_block(key, b"\x00" * 16)
    s = _ghash(h, aad, ct)
    j0 = iv + b"\x00\x00\x00\x01"
    expected = bytes(a ^ b for a, b in zip(_aes_encrypt_block(key, j0), s.to_bytes(16, "big")))
    if not hmac.compare_digest(expected, tag):
        raise ValueError("AES-GCM tag mismatch")
    out = bytearray()
    counter = 2
    for i in range(0, len(ct), 16):
        block = ct[i:i + 16]
        ctr = iv + counter.to_bytes(4, "big")
        keystream = _aes_encrypt_block(key, ctr)
        out += bytes(a ^ b for a, b in zip(block, keystream))
        counter += 1
    return bytes(out)


# ---------------------------------------------------------------- ECDH P-256
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _ec_mul(k, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _ec_add(result, addend)
        addend = _ec_add(addend, addend)
        k >>= 1
    return result


def _ecdh_keypair():
    while True:
        priv = int.from_bytes(secrets.token_bytes(32), "big") % (_N - 1) + 1
        pub = _ec_mul(priv, (_GX, _GY))
        if pub is not None:
            break
    pub_raw = b"\x04" + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")
    return priv, pub_raw


def _ecdh_shared(priv, peer_raw):
    if len(peer_raw) != 65 or peer_raw[0] != 0x04:
        raise ValueError("bad peer public key")
    x = int.from_bytes(peer_raw[1:33], "big")
    y = int.from_bytes(peer_raw[33:65], "big")
    shared = _ec_mul(priv, (x, y))
    if shared is None:
        raise ValueError("ECDH failed")
    return shared[0].to_bytes(32, "big")


def _hkdf_sha256(salt, ikm, info, length=32):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        out += t
        counter += 1
    return out[:length]


# ---------------------------------------------------------------- HTTP
def _http(method, url, body=None, headers=None, timeout=20):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()
    except Exception:
        raise


class Spider(BaseSpider):
    def init(self, extend=""):
        self._cookie = COOKIE or ""
        self._ua = UA
        self._session = None  # {"sid": str, "key": bytes, "expiresAt": ms}
        self._snapshot = ""
        self._snap_key = ""
        self._index = None  # {"actors": [...], "makers": [...]}，扫库一次后本会话内缓存
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                if "=" in extend:
                    cfg = {"cookie": extend}
        if isinstance(cfg, dict):
            if cfg.get("cookie"):
                self._cookie = str(cfg["cookie"])
            tickets = cfg.get("tickets") or {}
            if isinstance(tickets, dict):
                t = tickets.get(HOST) or tickets.get(BASE) or {}
                if isinstance(t, dict):
                    if t.get("cookie"):
                        self._cookie = str(t["cookie"])
                    if t.get("ua"):
                        self._ua = str(t["ua"])

    # ------------------------------------------------------------ headers
    def _headers(self, extra=None):
        h = {
            "User-Agent": self._ua,
            "Origin": BASE,
            "Referer": BASE + "/",
            "Accept": "application/json, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self._cookie:
            h["Cookie"] = self._cookie
        if extra:
            h.update(extra)
        return h

    # ------------------------------------------------------------ session
    def _new_session(self):
        priv, pub_raw = _ecdh_keypair()
        status, _ct, raw = _http(
            "POST", BASE + "/api/crypto/session",
            {"v": 1, "publicKey": _b64u_encode(pub_raw)},
            self._headers(), timeout=20)
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            data = {}
        if status == 403:
            reason = (data or {}).get("reason", "")
            if reason in ("verify", "origin"):
                raise _VerifyNeeded()
            raise _Blocked()
        if status != 200 or not isinstance(data, dict):
            if raw[:15].lower().find(b"cloudflare") >= 0 or b"Attention Required" in raw[:2000]:
                raise _Blocked()
            raise _Blocked()
        sid = data.get("sid") or ""
        expires = data.get("expiresAt") or 0
        peer = _b64u_decode(data.get("publicKey") or "")
        salt = _b64u_decode(data.get("salt") or "")
        if data.get("v") != 1 or not sid or len(peer) != 65 or len(salt) != 32:
            raise _Blocked()
        shared = _ecdh_shared(priv, peer)
        key = _hkdf_sha256(salt, shared, ("ltx-api-response-v1:" + sid).encode("utf-8"), 32)
        self._session = {"sid": sid, "key": key, "expiresAt": int(expires)}

    def _ensure_session(self):
        s = self._session
        if s and s.get("expiresAt", 0) > int(time.time() * 1000) + 5000:
            return s
        self._session = None
        self._new_session()
        return self._session

    # ------------------------------------------------------------ API
    def _api(self, path, method="GET", body=None):
        for attempt in range(2):
            sess = self._ensure_session()
            rid = _b64u_encode(secrets.token_bytes(16))
            url = BASE + path
            headers = self._headers({
                "X-LTX-Session": sess["sid"],
                "X-LTX-Request": rid,
            })
            status, ct, raw = _http(method, url, body, headers, timeout=25)
            if status == 428:
                try:
                    data = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    data = {}
                if isinstance(data, dict) and data.get("reason") == "cryptoSession" and attempt == 0:
                    self._session = None
                    continue
            if status == 403:
                try:
                    data = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    data = {}
                if isinstance(data, dict) and data.get("reason") in ("verify", "origin"):
                    raise _VerifyNeeded()
                raise _Blocked()
            if "application/vnd.ltx.encrypted+json" not in (ct or ""):
                if status != 200:
                    raise _Blocked()
                raise _Blocked()
            try:
                env = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                raise _Blocked()
            if (env.get("v") != 1 or env.get("sid") != sess["sid"]
                    or env.get("rid") != rid):
                raise _Blocked()
            encoding = env.get("encoding") or "identity"
            if encoding not in ("identity", "gzip"):
                raise _Blocked()
            iv = _b64u_decode(env.get("iv") or "")
            if len(iv) != 12:
                raise _Blocked()
            parsed = urllib.parse.urlparse(url)
            path_q = parsed.path + (("?" + parsed.query) if parsed.query else "")
            aad = json.dumps(
                ["ltx-api-response-v1", sess["sid"], rid, method.upper(),
                 path_q, status, encoding],
                separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            try:
                plain = _aes_gcm_decrypt(sess["key"], iv, _b64u_decode(env.get("body") or ""), aad)
            except Exception:
                raise _Blocked()
            if encoding == "gzip":
                plain = gzip.decompress(plain)
            return json.loads(plain.decode("utf-8", "replace"))
        raise _Blocked()

    def _query(self, params, key=""):
        body = dict(params or {})
        if key and key == self._snap_key and self._snapshot:
            body["snapshot"] = self._snapshot
        try:
            data = self._api("/api/items/query", "POST", body)
        except Exception:
            raise
        if isinstance(data, dict) and data.get("snapshot"):
            self._snapshot = data["snapshot"]
            self._snap_key = key
        return data

    def _scan_index(self):
        """扫全库一次，聚合女优/厂牌名单（按作品数倒序，封面取第一部作品）。

        站点没有现成的女优/厂牌接口，所以从接口实时拉全部作品再聚合；
        站点上新后，下次进壳子重新扫，名单跟着变。扫一次的结果缓存在
        self._index 里，本会话内不再重复扫。
        """
        if self._index is not None:
            return self._index
        actors = {}
        makers = {}
        offset = 0
        total = None
        seen = 0
        for _ in range(40):  # 上限兜底，避免接口异常时死循环
            data = self._query(
                {"status": "all", "sort": {"field": "score", "dir": "desc"},
                 "offset": offset, "limit": SCAN_LIMIT},
                key="scan")
            items = (data or {}).get("items") or []
            if total is None:
                try:
                    total = int((data or {}).get("total") or 0)
                except Exception:
                    total = 0
            if not items:
                break
            for it in items:
                if not isinstance(it, dict):
                    continue
                cover = it.get("cover") or ""
                for a in (it.get("actors") or []):
                    name = str(a).strip()
                    if not name:
                        continue
                    ent = actors.setdefault(
                        name, {"name": name, "count": 0, "cover": ""})
                    ent["count"] += 1
                    if not ent["cover"] and cover:
                        ent["cover"] = cover
                mk = str(it.get("maker") or "").strip()
                if mk:
                    ent = makers.setdefault(
                        mk, {"name": mk, "count": 0, "cover": ""})
                    ent["count"] += 1
                    if not ent["cover"] and cover:
                        ent["cover"] = cover
            seen += len(items)
            offset += len(items)
            if total and seen >= total:
                break
            if len(items) < SCAN_LIMIT:
                break
        actor_list = sorted(
            actors.values(), key=lambda e: (-e["count"], e["name"]))
        maker_list = sorted(
            makers.values(), key=lambda e: (-e["count"], e["name"]))
        self._index = {"actors": actor_list, "makers": maker_list,
                       "total": total or seen}
        return self._index

    def _index_page(self, kind, pg):
        idx = self._scan_index()
        rows = idx["actors"] if kind == "actors" else idx["makers"]
        pg = int(pg or 1)
        pagecount = max((len(rows) + PAGE_SIZE - 1) // PAGE_SIZE, 1)
        start = (pg - 1) * PAGE_SIZE
        items = []
        for ent in rows[start:start + PAGE_SIZE]:
            prefix = "actor:" if kind == "actors" else "maker:"
            items.append({
                "vod_id": prefix + ent["name"],
                "vod_name": ent["name"],
                "vod_pic": ent["cover"],
                "vod_remarks": "%d 部" % ent["count"],
                "vod_content": ent["name"],
            })
        return {"list": items, "page": pg, "pagecount": pagecount,
                "limit": PAGE_SIZE, "total": len(rows)}

    # ------------------------------------------------------------ mapping
    def _item_to_vod(self, it):
        if not isinstance(it, dict):
            return None
        code = str(it.get("code") or "").strip()
        if not code:
            return None
        title = it.get("title_zh") or it.get("title") or code
        actors = it.get("actors") or []
        if isinstance(actors, str):
            actors = [actors]
        score = it.get("score")
        remarks = ""
        if score is not None:
            try:
                remarks = "★%.2f" % float(score)
            except Exception:
                remarks = str(score)
        if it.get("date"):
            remarks = (remarks + " · " + str(it["date"])) if remarks else str(it["date"])
        if it.get("maker"):
            remarks = (remarks + " · " + str(it["maker"])) if remarks else str(it["maker"])
        if it.get("pending"):
            remarks += " · 待确认"
        return {
            "vod_id": code,
            "vod_name": str(title).strip(),
            "vod_pic": it.get("cover") or "",
            "vod_year": str(it.get("date") or "")[:4],
            "vod_area": "",
            "vod_actor": ", ".join(str(a) for a in actors),
            "vod_director": str(it.get("maker") or ""),
            "vod_remarks": remarks,
            "vod_content": str(title).strip(),
        }

    def _list_result(self, data, pg):
        items = []
        total = 0
        if isinstance(data, dict):
            total = int(data.get("total") or 0)
            for it in data.get("items") or []:
                v = self._item_to_vod(it)
                if v:
                    items.append(v)
        pg = int(pg or 1)
        if total:
            pagecount = (total + PAGE_SIZE - 1) // PAGE_SIZE
        else:
            pagecount = pg + 1 if len(items) >= PAGE_SIZE else pg
        return {
            "list": items,
            "page": pg,
            "pagecount": max(pagecount, 1),
            "limit": len(items) or PAGE_SIZE,
            "total": total,
        }

    # ------------------------------------------------------------ TVBox
    def homeContent(self, filter=False):
        classes = [
            {"type_id": "all", "type_name": "全部作品"},
            {"type_id": "ok", "type_name": "已确认"},
            {"type_id": "pending", "type_name": "待确认"},
            {"type_id": "added", "type_name": "最新入库"},
            {"type_id": "date", "type_name": "最新发行"},
            {"type_id": "size", "type_name": "最大"},
            {"type_id": "comments", "type_name": "最多评论"},
            {"type_id": "ed2k", "type_name": "仅 ed2k"},
            {"type_id": "magnet", "type_name": "仅磁力"},
            {"type_id": "sub", "type_name": "仅中字"},
            {"type_id": "actors", "type_name": "女优"},
            {"type_id": "makers", "type_name": "厂牌"},
        ]
        return {"class": classes, "filters": {}}

    def _query_for_tid(self, tid):
        q = {"status": "all", "sort": {"field": "score", "dir": "desc"},
             "limit": PAGE_SIZE}
        if tid in ("all", "", None):
            pass
        elif tid == "ok":
            q["status"] = "ok"
        elif tid == "pending":
            q["status"] = "pending"
        elif tid == "added":
            q["sort"] = {"field": "added", "dir": "desc"}
        elif tid == "date":
            q["sort"] = {"field": "date", "dir": "desc"}
        elif tid == "size":
            q["sort"] = {"field": "size", "dir": "desc"}
        elif tid == "comments":
            q["sort"] = {"field": "comments", "dir": "desc"}
        elif tid == "ed2k":
            q["type"] = "ed2k"
        elif tid == "magnet":
            q["type"] = "magnet"
        elif tid == "sub":
            q["sub"] = True
        elif str(tid).startswith("maker:"):
            q["maker"] = str(tid)[6:]
        elif str(tid).startswith("actor:"):
            q["actor"] = str(tid)[6:]
        return q

    def homeVideoContent(self):
        try:
            data = self._query(
                {"status": "all", "sort": {"field": "score", "dir": "desc"},
                 "offset": 0, "limit": PAGE_SIZE}, key="home")
        except _VerifyNeeded:
            return {"list": [], "msg": VERIFY_MSG}
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception:
            return {"list": []}
        return self._list_result(data, 1)

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        if str(tid or "") in ("actors", "makers"):
            try:
                return self._index_page(str(tid), pg)
            except _VerifyNeeded:
                return {"list": [], "page": pg, "pagecount": 1,
                        "limit": PAGE_SIZE, "total": 0, "msg": VERIFY_MSG}
            except _Blocked:
                return {"list": [], "page": pg, "pagecount": 1,
                        "limit": PAGE_SIZE, "total": 0, "msg": BLOCK_MSG}
            except Exception:
                return {"list": [], "page": pg, "pagecount": 1,
                        "limit": PAGE_SIZE, "total": 0}
        q = self._query_for_tid(str(tid or "all"))
        q["offset"] = (pg - 1) * PAGE_SIZE
        q["limit"] = PAGE_SIZE
        try:
            data = self._query(q, key="cat:" + str(tid))
        except _VerifyNeeded:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0, "msg": VERIFY_MSG}
        except _Blocked:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0, "msg": BLOCK_MSG}
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}
        return self._list_result(data, pg)

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        q = {"q": str(key or "").strip(), "status": "all",
             "sort": {"field": "score", "dir": "desc"},
             "offset": (pg - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
        try:
            data = self._query(q, key="q:" + str(key))
        except _VerifyNeeded:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0, "msg": VERIFY_MSG}
        except _Blocked:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0, "msg": BLOCK_MSG}
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}
        return self._list_result(data, pg)

    def detailContent(self, ids):
        code = ""
        if isinstance(ids, (list, tuple)) and ids:
            code = str(ids[0]).strip()
        else:
            code = str(ids or "").strip()
        code = code.split("@@")[0]
        # 女优/厂牌卡片：点开是该女优/厂牌的作品列表（每集一部作品）
        if code.startswith("actor:") or code.startswith("maker:"):
            name = code.split(":", 1)[1]
            q = {"status": "all", "sort": {"field": "score", "dir": "desc"},
                 "limit": 100}
            if code.startswith("actor:"):
                q["actor"] = name
            else:
                q["maker"] = name
            try:
                data = self._query(q, key="detail:" + code)
            except _VerifyNeeded:
                return {"list": [], "msg": VERIFY_MSG}
            except _Blocked:
                return {"list": [], "msg": BLOCK_MSG}
            except Exception:
                return {"list": []}
            items = (data or {}).get("items") or []
            eps = []
            for it in items:
                v = self._item_to_vod(it)
                if v:
                    eps.append("%s$%s" % (v["vod_name"], v["vod_id"]))
            if not eps:
                return {"list": []}
            vod = {
                "vod_id": code,
                "vod_name": name,
                "vod_pic": (items[0].get("cover") or ""),
                "vod_remarks": "%d 部" % len(items),
                "vod_content": name,
                "vod_play_from": "作品",
                "vod_play_url": "#".join(eps),
            }
            return {"list": [vod]}
        try:
            data = self._query(
                {"wantCodes": [code], "status": "all", "metadata": False,
                 "limit": 1}, key="")
            items = (data or {}).get("items") or []
            if not items:
                data = self._query(
                    {"q": code, "status": "all", "limit": 5}, key="q:" + code)
                items = (data or {}).get("items") or []
        except _VerifyNeeded:
            return {"list": [], "msg": VERIFY_MSG}
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception:
            return {"list": []}
        it = None
        for cand in items:
            if str(cand.get("code") or "").upper() == code.upper():
                it = cand
                break
        if it is None and items:
            it = items[0]
        if not it:
            return {"list": []}
        vod = self._item_to_vod(it) or {"vod_id": code, "vod_name": code}
        link = str(it.get("link") or "")
        size_text = ""
        if link.startswith("ed2k://"):
            parts = link.split("|")
            try:
                size_bytes = int(parts[3])
                size_text = "%.1fG" % (size_bytes / (1024 ** 3))
            except Exception:
                pass
        lines = []
        if it.get("title"):
            lines.append("原标题：" + str(it["title"]))
        if it.get("title_zh"):
            lines.append("中文标题：" + str(it["title_zh"]))
        actors = it.get("actors") or []
        if actors:
            lines.append("女优：" + ", ".join(str(a) for a in actors))
        if it.get("maker"):
            lines.append("片商：" + str(it["maker"]))
        if it.get("date"):
            lines.append("发行：" + str(it["date"]))
        if it.get("added"):
            lines.append("入库：" + str(it["added"]))
        if it.get("score") is not None:
            extra = ""
            if it.get("rawScore") is not None:
                extra = "（javdb 原始 %.2f 分，%s 人评价）" % (
                    float(it["rawScore"]), it.get("votes") or 0)
            lines.append("评分：%.2f %s" % (float(it["score"]), extra))
        if it.get("people") is not None or it.get("likers") is not None:
            lines.append("评论 %s 人 · 点赞 %s 人 · 加入片单 %s 人" % (
                it.get("people") or 0, it.get("likers") or 0, it.get("lists") or 0))
        if size_text:
            lines.append("大小：" + size_text)
        if it.get("hasSub"):
            lines.append("中文字幕：有（subtitlecat，多为机翻）")
        if it.get("pending"):
            lines.append("状态：待确认（未收录于 Jasna 汇总表）")
        else:
            lines.append("状态：已确认")
        lines.append("下载链接是 ed2k / 磁力直链，不是站内在线播放；点播放会把链接交出去。")
        vod["vod_content"] = "\n".join(lines)
        if link:
            kind = "ed2k" if link.startswith("ed2k://") else (
                "磁力" if link.startswith("magnet:") else "下载")
            vod["vod_play_from"] = kind
            vod["vod_play_url"] = "下载$" + link
        else:
            vod["vod_play_from"] = "下载"
            vod["vod_play_url"] = ""
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        link = str(id or "").strip()
        if link.startswith("ed2k://") or link.startswith("magnet:"):
            return {"parse": 0, "url": link,
                    "header": {"User-Agent": self._ua, "Referer": BASE + "/"}}
        # id 可能是番号：再查一次拿链接
        try:
            data = self._query(
                {"wantCodes": [link], "status": "all", "metadata": False,
                 "limit": 1}, key="")
            items = (data or {}).get("items") or []
            if items and items[0].get("link"):
                return {"parse": 0, "url": str(items[0]["link"]),
                        "header": {"User-Agent": self._ua, "Referer": BASE + "/"}}
        except _VerifyNeeded:
            return {"parse": 0, "url": "", "msg": VERIFY_MSG}
        except _Blocked:
            return {"parse": 0, "url": "", "msg": BLOCK_MSG}
        except Exception:
            pass
        return {"parse": 0, "url": "", "msg": "这部没有下载链接"}

    def localProxy(self, param):
        return [404, "text/plain", ""]
