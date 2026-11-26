# -*- coding: utf-8 -*-
"""推特APP · TVBox / dsplayer Python 源（新版接口 ver=3.1.1）

修复说明（2026-11-20）
-----------------------
旧版（ver=1.4.4）写死的 5 个域名后缀 pdcqllfomw.work / hfbtpixjso.work ... 已全部过期，
DNS 被域名停放商接管（访问返回 welcome 停放页），旧版 CloudFront 源站也只剩默认 nginx。
也就是说：旧版“没数据”的根因是**后端换了域名和鉴权协议**，不是本地代码写错。
本版按 App 当前协议（UA 里的 SuiRui/twitter/ver=3.1.1）重写：

  1. 接口域名：https://<随机子域>.opf1x78l.work（服务端泛解析，任意子域可用；随机子域防封锁）
  2. 登录：POST /api/user/traveler/<动态路径>/login
       路径 = hex(epoch)[:8]+uuid 前 16 位；密钥 = 路径切片翻转；请求/响应用 AES-128-ECB
  3. 业务接口：GET 带 deviceId/t/s/aut 头，s = md5(时间戳第 4~8 位)；
       响应 encData 用 AES-128-CBC 解密，key=iv=token[2:18]
  4. 播放：/api/m3u8/decode/by/id?videoId= 直接返回带签名的 m3u8，走 localProxy 透传
  5. 封面：图片前 100 字节被 XOR 加密，走 localProxy 解密后再给播放器

只依赖 Python 标准库（有 pycryptodome 时自动用它加速），不依赖 requests / Crypto 必装。
"""

import base64
import gzip
import hashlib
import json
import random
import re
import string
import time
import uuid
from urllib.parse import parse_qsl, quote, unquote, urlencode
from urllib.request import Request, urlopen

try:
    from base.spider import Spider as BaseSpider
except Exception:  # 本地自测/非常规壳
    class BaseSpider(object):
        def getCache(self, key):
            return None

        def setCache(self, key, value):
            return 'fail'

        def delCache(self, key):
            return 'fail'


# --------------------------------------------------------------------------
# AES：优先 pycryptodome（快 70 倍），没有就用纯 Python 实现兜底
# --------------------------------------------------------------------------
try:
    from Crypto.Cipher import AES as _AES  # noqa: N816
except Exception:
    _AES = None

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
_SBOX_INV = [0] * 256
for _i in range(256):
    _SBOX_INV[_SBOX[_i]] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(b):
    return ((b << 1) ^ 0x11b) & 0xff if b & 0x80 else (b << 1) & 0xff


def _gf_mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r & 0xff


def _sub_bytes(st, sbox):
    for i in range(16):
        st[i] = sbox[st[i]]


def _shift_rows(st):
    st[1], st[5], st[9], st[13] = st[5], st[9], st[13], st[1]
    st[2], st[6], st[10], st[14] = st[10], st[14], st[2], st[6]
    st[3], st[7], st[11], st[15] = st[15], st[3], st[7], st[11]


def _inv_shift_rows(st):
    st[1], st[5], st[9], st[13] = st[13], st[1], st[5], st[9]
    st[2], st[6], st[10], st[14] = st[10], st[14], st[2], st[6]
    st[3], st[7], st[11], st[15] = st[7], st[11], st[15], st[3]


def _mix_cols(st):
    for c in range(0, 16, 4):
        a0, a1, a2, a3 = st[c], st[c + 1], st[c + 2], st[c + 3]
        st[c] = _gf_mul(a0, 2) ^ _gf_mul(a1, 3) ^ a2 ^ a3
        st[c + 1] = a0 ^ _gf_mul(a1, 2) ^ _gf_mul(a2, 3) ^ a3
        st[c + 2] = a0 ^ a1 ^ _gf_mul(a2, 2) ^ _gf_mul(a3, 3)
        st[c + 3] = _gf_mul(a0, 3) ^ a1 ^ a2 ^ _gf_mul(a3, 2)


def _inv_mix_cols(st):
    for c in range(0, 16, 4):
        a0, a1, a2, a3 = st[c], st[c + 1], st[c + 2], st[c + 3]
        st[c] = _gf_mul(a0, 14) ^ _gf_mul(a1, 11) ^ _gf_mul(a2, 13) ^ _gf_mul(a3, 9)
        st[c + 1] = _gf_mul(a0, 9) ^ _gf_mul(a1, 14) ^ _gf_mul(a2, 11) ^ _gf_mul(a3, 13)
        st[c + 2] = _gf_mul(a0, 13) ^ _gf_mul(a1, 9) ^ _gf_mul(a2, 14) ^ _gf_mul(a3, 11)
        st[c + 3] = _gf_mul(a0, 11) ^ _gf_mul(a1, 13) ^ _gf_mul(a2, 9) ^ _gf_mul(a3, 14)


def _key_expand(key):
    nk = 4
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    for i in range(nk, 44):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w


def _add_round_key(st, w, rnd):
    base = 4 * rnd
    for i in range(16):
        st[i] ^= w[base + i // 4][i % 4]


def _encrypt_block(block, w):
    st = list(block)
    _add_round_key(st, w, 0)
    for rnd in range(1, 10):
        _sub_bytes(st, _SBOX)
        _shift_rows(st)
        _mix_cols(st)
        _add_round_key(st, w, rnd)
    _sub_bytes(st, _SBOX)
    _shift_rows(st)
    _add_round_key(st, w, 10)
    return st


def _decrypt_block(block, w):
    st = list(block)
    _add_round_key(st, w, 10)
    _inv_shift_rows(st)
    _sub_bytes(st, _SBOX_INV)
    for rnd in range(9, 0, -1):
        _add_round_key(st, w, rnd)
        _inv_mix_cols(st)
        _inv_shift_rows(st)
        _sub_bytes(st, _SBOX_INV)
    _add_round_key(st, w, 0)
    return st


def _pkcs7_unpad(data):
    if not data:
        return b''
    n = data[-1]
    if 0 < n <= 16 and len(data) >= n:
        return data[:-n]
    return data


def _pp_ecb_encrypt(plain, key):
    w = _key_expand(key)
    padn = 16 - len(plain) % 16
    padded = plain + bytes([padn]) * padn
    out = b''
    for i in range(0, len(padded), 16):
        out += bytes(_encrypt_block(padded[i:i + 16], w))
    return out


def _pp_ecb_decrypt(data, key):
    w = _key_expand(key)
    out = bytearray()
    for i in range(0, len(data) - len(data) % 16, 16):
        out += bytes(_decrypt_block(data[i:i + 16], w))
    return _pkcs7_unpad(bytes(out))


def _pp_cbc_decrypt(data, key, iv):
    w = _key_expand(key)
    prev = list(iv)
    out = bytearray()
    for i in range(0, len(data) - len(data) % 16, 16):
        blk = data[i:i + 16]
        dec = _decrypt_block(blk, w)
        out += bytes([dec[j] ^ prev[j] for j in range(16)])
        prev = list(blk)
    return _pkcs7_unpad(bytes(out))


def aes_ecb_encrypt(plain, key):
    key = _key16(key)
    if _AES is not None:
        try:
            padn = 16 - len(plain) % 16
            return _AES.new(key, _AES.MODE_ECB).encrypt(plain + bytes([padn]) * padn)
        except Exception:
            pass
    return _pp_ecb_encrypt(plain, key)


def aes_ecb_decrypt(data, key):
    key = _key16(key)
    if _AES is not None:
        try:
            return _pkcs7_unpad(_AES.new(key, _AES.MODE_ECB).decrypt(data))
        except Exception:
            pass
    return _pp_ecb_decrypt(data, key)


def aes_cbc_decrypt(data, key, iv):
    key = _key16(key)
    iv = _key16(iv)
    if _AES is not None:
        try:
            return _pkcs7_unpad(_AES.new(key, _AES.MODE_CBC, iv).decrypt(data))
        except Exception:
            pass
    return _pp_cbc_decrypt(data, key, iv)


def _key16(key):
    key = key if isinstance(key, (bytes, bytearray)) else str(key).encode('utf-8')
    key = bytes(key)
    if len(key) == 16:
        return key
    if len(key) > 16:
        return key[:16]
    return key + b'\x00' * (16 - len(key))


# --------------------------------------------------------------------------
# 封面图：前 100 字节 XOR（全站同一把钥匙），其余是明文
# --------------------------------------------------------------------------
PIC_KEY = b'2020-zq3-888'
PIC_HEAD = 100
IMG_MAGIC = ((b'\xff\xd8\xff', 'image/jpeg'),
             (b'RIFF', 'image/webp'),
             (b'\x89PNG\r\n\x1a\n', 'image/png'),
             (b'GIF8', 'image/gif'))


def xor_pic(data, head=PIC_HEAD):
    if not data:
        return b''
    m = min(head, len(data))
    out = bytearray(data)
    for i in range(m):
        out[i] ^= PIC_KEY[i % len(PIC_KEY)]
    return bytes(out)


def img_type(data):
    for magic, ctype in IMG_MAGIC:
        if data.startswith(magic):
            return ctype
    return ''


def decode_pic(data):
    """解封面：只异或前 100 字节；魔数对不上再整文件异或兜底。"""
    if not data:
        return b'', ''
    out = xor_pic(data)
    ctype = img_type(out)
    if ctype:
        return out, ctype
    alt = xor_pic(data, len(data))
    ctype = img_type(alt)
    if ctype:
        return alt, ctype
    return data, 'image/jpeg'


class Spider(BaseSpider):
    # 接口后缀；服务端是泛解析，任意子域都能通
    SUFFIXES = ('opf1x78l.work',)
    # 观察到的静态图床兜底（只给封面用，接口不走这里）
    PIC_HOSTS = ('https://972pb3r10qxz.dfgwsx.com/',)
    UA = ('Mozilla/5.0 (Linux; Android 14; 22127RK46C Build/TP1A.220624.014; wv) '
          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
          'Chrome/120.0.0.0 Mobile Safari/537.36/SuiRui/twitter/ver=3.1.1')
    PIC_RE = re.compile(r'(?:(?:jpe|image|img|cover|video|pic)/[^\s"\'&,;]+|[\w/\-.]+\.(?:jpg|jpeg|png|gif|webp|bmp))', re.I)

    def getName(self):
        return '推特APP'

    def getDependence(self):
        return []

    def init(self, extend=''):
        self.extend = extend or ''
        self.ua = self.UA
        self.device_id = self._did()
        self.host = ''
        self.token = None
        self._domain = ''
        self._auth_domain = ''
        self._classes = None
        self._classes_ts = 0
        self._pic_cache = {}
        self._pic_size = 0
        self._m3u_cache = {}
        self._item_cache = {}
        self._bad_hosts = {}
        self._home_ts = 0
        self._home_cache = None
        self._timeout = 7
        try:  # 上次跑通的子域缓存，省掉重新探测
            line = self.getCache('twline') or ''
            host = line.split('|', 1)[0] if '|' in line else line
            if host.startswith('http') and 'opf1x78l' in host:
                self.host = host
        except Exception:
            pass

    # ------------------------- 基础工具 -------------------------
    @staticmethod
    def _b64d(s):
        return base64.b64decode(s)

    @staticmethod
    def _b64e(b):
        return base64.b64encode(b).decode()

    def _md5(self, text):
        return hashlib.md5(str(text).encode('utf-8')).hexdigest()

    def _did(self):
        did = ''
        try:
            did = self.getCache('twdid') or ''
        except Exception:
            did = ''
        if not did:
            did = uuid.uuid4().hex
            try:
                self.setCache('twdid', did)
            except Exception:
                pass
        return did

    def _suffixes(self):
        out = list(self.SUFFIXES)
        ext = self.extend
        cfg = {}
        if isinstance(ext, dict):
            cfg = ext
        elif isinstance(ext, str) and ext.strip():
            s = ext.strip()
            if s.startswith('{'):
                try:
                    cfg = json.loads(s)
                except Exception:
                    cfg = {}
            elif '.' in s:
                cfg = {'suffix': s}
        extra = cfg.get('suffix') or cfg.get('suffixes') or cfg.get('host') or ''
        if isinstance(extra, str):
            extra = [x for x in re.split(r'[,\s]+', extra) if x]
        for x in extra or []:
            x = str(x).strip().strip('.')
            x = re.sub(r'^https?://', '', x).split('/', 1)[0]
            if x and x not in out:
                out.append(x)
        return out

    def _new_host(self):
        suffix = random.choice(self._suffixes())
        sub = ''.join(random.choice(string.ascii_lowercase + string.digits)
                      for _ in range(random.randint(6, 8)))
        return 'https://%s.%s' % (sub, suffix)

    def _rotate_host(self):
        now = time.time()
        for _ in range(6):
            host = self._new_host()
            if now - self._bad_hosts.get(host, 0) > 600:
                self.host = host
                return host
        self.host = self._new_host()
        return self.host

    def _mark_bad(self):
        if self.host:
            self._bad_hosts[self.host] = time.time()
        self.token = None

    # ------------------------- HTTP -------------------------
    def _http(self, url, data=None, headers=None, timeout=None):
        timeout = timeout or self._timeout
        hdrs = {
            'User-Agent': self.ua,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'identity',
            'Connection': 'close',
        }
        if headers:
            hdrs.update(headers)
        body = None
        if data is not None:
            if isinstance(data, (bytes, bytearray)):
                body = bytes(data)
            else:
                body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            hdrs.setdefault('Content-Type', 'application/json')
        req = Request(url, data=body, headers=hdrs, method='POST' if body else 'GET')
        try:
            resp = urlopen(req, timeout=timeout)
        except Exception as e:
            # 部分老设备根证书不全：校验失败时退回不校验
            if 'CERTIFICATE' not in str(e).upper() and 'SSL' not in str(e).upper():
                raise
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            resp = urlopen(req, timeout=timeout, context=ctx)
        try:
            raw = resp.read()
            if (resp.headers.get('Content-Encoding') or '').lower() == 'gzip':
                raw = gzip.decompress(raw)
            return raw, resp.headers
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _http_json(self, url, data=None, headers=None, timeout=None):
        raw, _ = self._http(url, data=data, headers=headers, timeout=timeout)
        return json.loads(raw.decode('utf-8', 'ignore'))

    # ------------------------- 登录 / 解密 -------------------------
    def _login_key(self, epoch):
        path = format(epoch, 'x')[:8] + uuid.uuid4().hex[:16]
        off = epoch % 8
        return path, path[off:16 + off][::-1]

    def _base_headers(self):
        t = str(int(time.time() * 1000))
        return {
            'User-Agent': self.ua,
            'Accept': 'application/json, text/plain, */*',
            'deviceId': self.device_id,
            't': t,
            's': self._md5(t[3:8]),
        }

    def _headers(self):
        h = self._base_headers()
        if self.token:
            h['aut'] = self.token
        return h

    def _login(self):
        epoch = int(time.time())
        path, ek = self._login_key(epoch)
        body = json.dumps({'deviceId': self.device_id, 'tt': 'a'}, separators=(',', ':'))
        enc = self._b64e(aes_ecb_encrypt(body.encode('utf-8'), ek.encode('utf-8')))
        h = self._base_headers()
        h['Content-Type'] = 'application/json'
        j = self._http_json(self.host + '/api/user/traveler/' + path + '/login',
                            data={'encStr': enc}, headers=h)
        if not isinstance(j, dict) or j.get('code') != 200 or not j.get('data'):
            return None
        plain = aes_ecb_decrypt(self._b64d(j['data']), ek.encode('utf-8'))
        ui = json.loads(plain.decode('utf-8', 'ignore'))
        token = ui.get('token')
        if token:
            self._remember_domain(ui)
        return token or None

    def _ensure_token(self):
        if self.token:
            return self.token
        for _ in range(2):
            if not self.host:
                self._rotate_host()
            try:
                tok = self._login()
                if tok:
                    self.token = tok
                    try:
                        self.setCache('twline', self.host + '|' + self.device_id)
                    except Exception:
                        pass
                    return tok
            except Exception:
                pass
            self._mark_bad()
            self._rotate_host()
        return None

    def _remember_domain(self, obj):
        if not isinstance(obj, dict):
            return
        d = obj.get('domain') or ''
        a = obj.get('authDomain') or ''
        if d:
            self._domain = str(d)
        if a:
            self._auth_domain = str(a)

    def _decode_enc(self, enc):
        tok = self.token or ''
        key = tok[2:18].encode('utf-8') or b'0' * 16
        return json.loads(aes_cbc_decrypt(self._b64d(enc), key, key).decode('utf-8', 'ignore'))

    def _parse_resp(self, j):
        if not isinstance(j, dict):
            return j
        self._remember_domain(j)
        enc = j.get('encData')
        if enc:
            try:
                d = self._decode_enc(enc)
                self._remember_domain(d)
                return d
            except Exception:
                return j
        return j

    def _get_once(self, path):
        j = self._http_json(self.host + path, headers=self._headers())
        if isinstance(j, dict):
            code = j.get('code')
            msg = str(j.get('msg') or '')
            if code in (400, 401, 1001) and ('token' in msg.lower() or '登录' in msg or '过期' in msg):
                self.token = None
                self._ensure_token()
                j = self._http_json(self.host + path, headers=self._headers())
        return self._parse_resp(j)

    def _api(self, path):
        """GET 业务接口（失败自动换域名 / 重登）。"""
        for attempt in range(2):
            if not self.host:
                self._rotate_host()
            if not self._ensure_token():
                # 登录都失败：多半是网络/整站被墙，别在这儿无限重试耗时间
                self._rotate_host()
                return {}
            try:
                data = self._get_once(path)
                if isinstance(data, (dict, list)):
                    return data
            except Exception:
                pass
            # 失败：换一个子域再试（服务器按子域分流，个别子域会被重置）
            self._mark_bad()
            self._rotate_host()
        return {}

    # ------------------------- 代理地址 -------------------------
    def _proxy_url(self, **params):
        base = ''
        try:
            if hasattr(self, 'getProxyUrl'):
                base = (self.getProxyUrl() or '').strip()
        except Exception:
            base = ''
        if not base:
            # 壳未提供代理地址：有直链就直接回直链（封面图），否则返回空串
            return params.get('u') or ''
        if 'do=py' not in base:
            base = base.rstrip('/') + '/proxy?do=py'
        elif '/proxy' not in base:
            base = base.replace('?do=py', '/proxy?do=py')
        params.setdefault('key', self.getName())
        sep = '&' if '?' in base else '?'
        return base + sep + urlencode(params)

    def _pic_url(self, rel, domain=''):
        if not rel:
            return ''
        if rel.startswith('http'):
            url = rel
        else:
            dom = domain or self._domain or ''
            if not dom:
                return ''
            url = dom.rstrip('/') + '/' + rel.lstrip('/')
        # 同时带相对路径：壳重启后 _domain 丢了也能靠 url 直接取
        return self._proxy_url(type='pic', p=rel.split('?', 1)[0], u=url)

    # ------------------------- 列表映射 -------------------------
    @staticmethod
    def _first(v):
        if isinstance(v, list):
            return v[0] if v else ''
        return v or ''

    def _remark(self, v):
        tags = ' '.join(v.get('tagTitles') or [])
        if tags:
            return tags[:18]
        pt = v.get('playTime') or 0
        try:
            sec = int(pt)
        except Exception:
            sec = 0
        if not sec:
            return ''
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        return ('%02d:%02d:%02d' % (h, m, s)) if h else ('%02d:%02d' % (m, s))

    def items(self, arr, clicked=False):
        res = []
        for v in arr or []:
            if not isinstance(v, dict):
                continue
            vid = str(v.get('videoId') or v.get('id') or '')
            if not vid:
                continue
            uid = str(v.get('userId') or '')
            nick = str(v.get('nickName') or '')
            title = str(v.get('title') or nick or vid)
            pic = self._first(v.get('coverImg')) or self._first(v.get('authCoverImg'))
            vod_id = '%s?%s?%s?%s' % (vid, uid, quote(nick, safe=''), quote(title, safe=''))
            if clicked:
                vod_id += 'click'
            self._item_cache[vid] = v
            res.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': self._pic_url(pic),
                'vod_remarks': self._remark(v),
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return res

    # ------------------------- 壳接口 -------------------------
    def homeContent(self, filter):
        now = time.time()
        if self._home_cache and now - self._home_ts < 60:
            return self._home_cache
        classes = [{'type_name': '精选', 'type_id': 'jx'}]
        try:
            d = self._api('/api/video/classifyList')
            names = []
            for c in (d.get('data') or []) if isinstance(d, dict) else []:
                tid = str(c.get('classifyId') or '')
                name = str(c.get('classifyTitle') or '')
                if tid and name:
                    classes.append({'type_name': name, 'type_id': tid})
                    names.append((tid, name))
            self._classes = classes
            self._classes_ts = int(time.time())
        except Exception:
            pass
        sort = [{'key': 'fl', 'name': '排序', 'value': [
            {'n': '最近更新', 'v': '1'}, {'n': '最多播放', 'v': '2'}, {'n': '好评榜', 'v': '3'}]}]
        filters = {}
        for c in classes:
            if c['type_id'] != 'jx':
                filters[c['type_id']] = sort
        filters['jx'] = [{'key': 'type', 'name': '精选', 'value': [
            {'n': '最新', 'v': '1'}, {'n': '最热', 'v': '2'},
            {'n': '好评榜', 'v': '3'}, {'n': '热榜', 'v': '4'}]}]
        out = {'class': classes, 'filters': filters}
        if len(classes) > 1:
            self._home_cache = out
            self._home_ts = now
        return out

    def homeVideoContent(self):
        return {'list': self.categoryContent('jx', '1', False, {'type': '1'}).get('list', [])}

    def _ext(self, extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                return json.loads(extend)
            except Exception:
                return {}
        return {}

    def categoryContent(self, tid, pg, filter, extend, *args, **kwargs):
        tid = str(tid or '')
        pg = str(pg or '1')
        ext = self._ext(extend)
        data = []
        try:
            if tid == 'jx':
                # 服务端 getRankVideos 的 type 1~4 返回同一份榜单，所以精选里：
                # 1/2/3 = 推荐分类的 最新/最多播放/好评榜，4 = 服务端热榜
                t = str(ext.get('type', '1'))
                if t == '4':
                    d = self._api('/api/video/getRankVideos?pageSize=20&page=%s&type=1' % pg)
                else:
                    d = self._api('/api/video/queryVideos?pageSize=20&page=%s&classifyId=2&sortType=%s'
                                  % (pg, t))
                data = d.get('data') if isinstance(d, dict) else []
            elif 'click' in tid:
                uid = tid.replace('click', '')
                d = self._api('/api/video/queryPersonVideoByType?pageSize=20&page=%s&userId=%s'
                              % (pg, uid))
                data = d.get('data') if isinstance(d, dict) else []
            else:
                d = self._api('/api/video/queryVideos?pageSize=20&page=%s&classifyId=%s&sortType=%s'
                              % (pg, tid, ext.get('fl', '1')))
                data = d.get('data') if isinstance(d, dict) else []
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
        lst = self.items(data, 'click' in tid)
        return {'list': lst, 'page': pg,
                'pagecount': (int(pg) + 1) if lst else int(pg),
                'limit': 20, 'total': 999999}

    def detailContent(self, array):
        raw = str(array[0] if array else '')
        if '?' not in raw and '%3f' in raw.lower():
            raw = unquote(raw)
        clicked = raw.endswith('click')
        if clicked:
            raw = raw[:-5]
        pp = raw.split('?', 3)
        vid = pp[0] if len(pp) > 0 else raw
        uid = pp[1] if len(pp) > 1 else ''
        nick = unquote(pp[2]) if len(pp) > 2 else ''
        title = unquote(pp[3]) if len(pp) > 3 else ''
        v = self._item_cache.get(vid) or {}
        name = (title or v.get('title') or nick or '推特APP').replace('$', '＄')
        # 作者可点：跳到该 UP 主的视频列表
        if clicked or not uid:
            director = nick or '推特APP'
        else:
            link = {'id': uid + 'click', 'name': nick or '推特APP'}
            director = '[a=cr:' + json.dumps(link, ensure_ascii=False) + '/]' + (nick or '推特APP') + '[/a]'
        pic = self._first(v.get('coverImg')) or self._first(v.get('authCoverImg'))
        content = ' '.join(v.get('tagTitles') or []) or name
        vod = {
            'vod_id': raw,
            'vod_name': name,
            'vod_pic': self._pic_url(pic),
            'vod_director': director,
            'vod_content': content,
            'vod_remarks': self._remark(v) if v else '',
            'vod_play_from': '推特专线',
            'vod_play_url': name + '$' + vid,
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        page = str(pg or '1')
        lst = []
        try:
            d = self._api('/api/search/keyWordVideo?searchWord=%s&pageSize=20&page=%s'
                          % (quote(str(key), safe=''), page))
            data = d.get('data') if isinstance(d, dict) else []
            if isinstance(data, list):
                lst = self.items(data)
        except Exception:
            lst = []
        return {'list': lst, 'page': page,
                'pagecount': (int(page) + 1) if lst else int(page),
                'limit': 20, 'total': 999999}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, str(pg or '1'))

    def playerContent(self, flag, id, vipFlags=None):
        vid = str(id)
        if '?' in vid:
            vid = vid.split('?', 1)[0]
        return {
            'parse': 0,
            'jx': 0,
            'playUrl': '',
            'url': self._proxy_url(type='m3u8', vid=vid),
            'header': {'User-Agent': self.ua},
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        pass

    def destroy(self):
        pass

    # ------------------------- 本地代理 -------------------------
    def proxy(self, param):
        return self.localProxy(param)

    def _params(self, param):
        if isinstance(param, dict):
            out = {}
            for k, v in param.items():
                try:
                    out[str(k)] = unquote(str(v))
                except Exception:
                    out[str(k)] = str(v)
            return out
        try:
            return dict(parse_qsl(str(param or '').lstrip('?'), keep_blank_values=True))
        except Exception:
            return {}

    def localProxy(self, param):
        p = self._params(param)
        tp = str(p.get('type') or p.get('do') or '')
        vid = str(p.get('vid') or '')
        pic = str(p.get('p') or p.get('u') or p.get('url') or p.get('img') or '')
        if not tp:
            tp = 'm3u8' if vid else 'pic'
        try:
            if tp in ('m3u8', 'play', 'video') or (vid and tp not in ('pic', 'img')):
                body = self._m3u8(vid)
                return [200, 'application/vnd.apple.mpegurl', body.encode('utf-8')]
            if pic:
                if not pic.startswith('http'):
                    m = self.PIC_RE.search(pic)
                    if m:
                        pic = m.group(0)
                data, ctype = self._load_pic(pic)
                if not data:
                    return [404, 'text/plain', b'']
                return [200, ctype, data]
        except Exception:
            pass
        return [200, 'text/plain', b'']

    def _m3u8(self, vid):
        vid = str(vid or '')
        if not vid:
            return ''
        hit = self._m3u_cache.get(vid)
        now = time.time()
        if hit and now - hit[0] < 25:
            return hit[1]
        text = ''
        for attempt in range(3):
            try:
                if not self.host:
                    self._rotate_host()
                self._ensure_token()
                raw, _ = self._http(self.host + '/api/m3u8/decode/by/id?videoId=%s' % quote(vid, safe=''),
                                    headers=self._headers())
                s = raw.decode('utf-8', 'ignore').strip()
                if s.startswith('#EXTM3U'):
                    text = s
                elif s.startswith('{'):
                    j = json.loads(s)
                    enc = j.get('encData') if isinstance(j, dict) else ''
                    if enc:
                        try:
                            text = aes_cbc_decrypt(self._b64d(enc),
                                                   (self.token or '')[2:18].encode('utf-8'),
                                                   (self.token or '')[2:18].encode('utf-8')).decode('utf-8', 'ignore')
                        except Exception:
                            text = ''
                if text.startswith('#EXTM3U'):
                    break
            except Exception:
                pass
            self._rotate_host()
        if text.startswith('#EXTM3U'):
            if len(self._m3u_cache) > 40:
                self._m3u_cache.clear()
            self._m3u_cache[vid] = (now, text)
        return text

    def _pic_candidates(self, pic):
        if pic.startswith('http'):
            return [pic]
        rel = pic.lstrip('/')
        out = []
        for dom in (self._domain, self._auth_domain) + self.PIC_HOSTS:
            if dom:
                u = dom.rstrip('/') + '/' + rel
                if u not in out:
                    out.append(u)
        return out

    def _load_pic(self, pic):
        hit = self._pic_cache.get(pic)
        if hit:
            return hit
        raw = b''
        for url in self._pic_candidates(pic):
            try:
                data, _ = self._http(url, headers={'User-Agent': self.ua, 'Accept': 'image/*,*/*'})
                if data:
                    raw = data
                    break
            except Exception:
                continue
        if not raw:
            return None, None
        out, ctype = decode_pic(raw)
        if self._pic_size + len(out) > 8 * 1024 * 1024 and self._pic_cache:
            self._pic_cache.clear()
            self._pic_size = 0
        self._pic_cache[pic] = (out, ctype)
        self._pic_size += len(out)
        return out, ctype


if __name__ == '__main__':
    sp = Spider()
    sp.init('')
    home = sp.homeContent(True)
    print('分类 %d 个: %s' % (len(home['class']),
                            ', '.join(c['type_name'] for c in home['class'])))
    cat = sp.categoryContent(home['class'][0]['type_id'], '1', False, {})
    print('列表 %d 条' % len(cat['list']))
    if cat['list']:
        first = cat['list'][0]
        print('首条:', first['vod_name'][:30], '|', first['vod_remarks'], '|', first['vod_pic'][:90])
        detail = sp.detailContent([first['vod_id']])['list'][0]
        print('详情:', detail['vod_name'][:26])
        play = sp.playerContent(detail['vod_play_from'], detail['vod_play_url'].split('$', 1)[1], None)
        print('播放:', play['url'][:110])
        # 直接调 localProxy 验证封面/取流
        param = dict(parse_qsl(play['url'].split('?', 1)[1]))
        r = sp.localProxy(param)
        print('m3u8 代理:', r[0], r[1], len(r[2]), 'EXTM3U' if r[2][:7] == b'#EXTM3U' else '')
        picparam = dict(parse_qsl(first['vod_pic'].split('?', 1)[1]))
        r2 = sp.localProxy(picparam)
        print('封面代理:', r2[0], r2[1], len(r2[2]))
        sr = sp.searchContent('美', False, '1')
        print('搜索 %d 条' % len(sr['list']))
