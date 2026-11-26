# -*- coding: utf-8 -*-
# 妻社

import base64
import gzip
import hashlib
import json
import os
import re
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


# FILL IN YOUR ACCOUNT HERE (or set it in the source extend config):
# Format: 'email:password' or 'username:password'
# Example: 'you@example.com:yourpassword'
# The extend config in the app overrides this value when set.
DEFAULT_ACCOUNT = 'YOUR_ACCOUNT:YOUR_PASSWORD'


class Spider(BaseSpider):
    VERSION = 'V1.1'
    DISCOVER = [
        'https://qsh5.xuanyipai.com/api.php',
        'https://qsh5.newfangchan.cn/api.php',
        'https://qs.qsazap2025by2.com/api.php',
    ]
    FALLBACK_HOST = 'h51.qisheh526222.org'
    UA = ('Mozilla/5.0 (Linux; Android 14; Redmi K70) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')
    CATS = [
        ('0', '推荐'), ('2', '妻友圈'), ('4', '夫妻认证交友'),
        ('5', '夫妻交换'), ('6', '调教露出'), ('7', '素质单男'),
        ('9', '淫妻分享'), ('11', '绿帽献妻'),
        ('22', '经验分享'), ('25', '母狗公示榜'), ('44', '妻社私密树洞'),
    ]

    def init(self, extend=""):
        self.extend = extend or ''

    def __init__(self):
        self._host = None
        self._token = None
        self._pubkey = None
        self._cache = {}
        self.extend = ''

    def _http(self, url, method='GET', body=None, headers=None):
        import gzip
        last_err = None
        for _ in range(3):
            try:
                import urllib.request
                hd = {'User-Agent': self.UA, 'Accept-Encoding': 'gzip'}
                if headers:
                    hd.update(headers)
                data = None
                if body is not None:
                    data = body if isinstance(body, bytes) else body.encode('utf-8')
                req = urllib.request.Request(url, data=data, headers=hd, method=method)
                raw = None
                is_gzip = True
                try:
                    with urllib.request.urlopen(req, timeout=20) as r:
                        is_gzip = (r.headers.get('Content-Encoding') or '').lower() == 'gzip'
                        raw = r.read()
                except Exception as e:
                    partial = getattr(e, 'partial', None)
                    if partial:
                        raw = partial
                    else:
                        raise
                if raw is None:
                    raise Exception('empty response')
                if is_gzip:
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                try:
                    return json.loads(raw.decode('utf-8', 'ignore'))
                except Exception:
                    last_err = Exception('bad json')
                    continue
            except Exception as e:
                last_err = e
                continue
        return {'code': -1, 'msg': str(last_err)}

    def _discover_host(self):
        if self._host:
            return self._host
        for u in self.DISCOVER:
            try:
                r = self._http(u)
                if isinstance(r, dict) and r.get('domain'):
                    self._host = r['domain']
                    return self._host
            except Exception:
                continue
        self._host = self.FALLBACK_HOST
        return self._host

    def _sign(self, action):
        host = self._discover_host()
        s = 'url={}&version={}&time=DATA&domain={}'.format(action, self.VERSION, host)
        return hashlib.md5(s.encode('utf-8')).hexdigest()

    def _api(self, action, params=None, method='GET', body=None):
        host = self._discover_host()
        q = {
            'sign': self._sign(action),
            'version': self.VERSION,
            'token': self._token or '',
            'pushcid': '',
            'devicebrand': 'Xiaomi',
            'platform': 'h5',
        }
        if params:
            q.update(params)
        qs = '&'.join('{}={}'.format(k, self._q(v)) for k, v in q.items())
        url = 'https://{}/source/plugin/qsts_app/index.php/{}?{}'.format(host, action, qs)
        hd = {}
        if body is not None:
            hd['Content-Type'] = 'application/json'
            body = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
        return self._http(url, method=method, body=body, headers=hd)

    @staticmethod
    def _q(v):
        try:
            from urllib.parse import quote
            return quote(str(v), safe='')
        except Exception:
            return str(v)

    @staticmethod
    def _der_read(data, pos):
        tag = data[pos]
        pos += 1
        ln = data[pos]
        pos += 1
        if ln & 0x80:
            n = ln & 0x7F
            ln = int.from_bytes(data[pos:pos + n], 'big')
            pos += n
        return tag, data[pos:pos + ln], pos + ln

    @classmethod
    def _parse_spki(cls, b64):
        der = base64.b64decode(b64)
        _, spki, _ = cls._der_read(der, 0)
        _, _, p = cls._der_read(spki, 0)
        _, bitstr, _ = cls._der_read(spki, p)
        _, rsapub, _ = cls._der_read(bitstr, 1)
        _, n_b, p2 = cls._der_read(rsapub, 0)
        _, e_b, _ = cls._der_read(rsapub, p2)
        return int.from_bytes(n_b, 'big'), int.from_bytes(e_b, 'big')

    @staticmethod
    def _rsa_encrypt_long(data, n, e):
        k = (n.bit_length() + 7) // 8
        out = []
        for i in range(0, len(data), k - 11):
            chunk = data[i:i + k - 11]
            ps_len = k - len(chunk) - 3
            ps = bytearray()
            while len(ps) < ps_len:
                b = os.urandom(1)[0]
                if b != 0:
                    ps.append(b)
            em = b'\x00\x02' + bytes(ps) + b'\x00' + chunk
            c = pow(int.from_bytes(em, 'big'), e, n)
            out.append(c.to_bytes(k, 'big').hex())
        return ''.join(out)

    def _login(self):
        if self._token:
            return True
        ext = (getattr(self, 'extend', '') or '').strip() or DEFAULT_ACCOUNT
        if not ext or ext == 'YOUR_ACCOUNT:YOUR_PASSWORD':
            return False
        m = re.split(r'[：:]', ext, maxsplit=1)
        if len(m) < 2:
            return False
        account, password = m[0].strip(), m[1].strip()
        if not account or not password:
            return False
        if '@' in account:
            body = {'phone': account, 'code': '', 'username': '',
                    'password': password, 'password2': '', 'type': 'email'}
        else:
            body = {'phone': '', 'code': '', 'username': account,
                    'password': password, 'password2': '', 'type': 'user'}
        r = self._api('user.login', method='POST', body=body)
        if not isinstance(r, dict) or r.get('code') != 200:
            return False
        member = (r.get('data') or {}).get('member') or {}
        uid, token = member.get('uid'), member.get('token')
        if not uid or not token:
            return False
        cfg = self._api('config.init')
        try:
            pubkey = cfg['data']['config']['pluginSet']['publickey']
            n, e = self._parse_spki(pubkey.strip())
        except Exception:
            return False
        payload = json.dumps({'version': 'v1', 'uid': uid, 'token': token},
                             ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self._token = self._rsa_encrypt_long(payload, n, e)
        self._pubkey = (n, e)
        return True

    def _videos_of(self, t):
        videos = []
        cover = ''
        try:
            atts = ((t.get('attachData') or {}).get('data') or [])
        except Exception:
            atts = []
        for a in atts:
            if not isinstance(a, dict):
                continue
            url = a.get('defurl') or a.get('attachment') or ''
            if a.get('isimage') == '1' or a.get('isimage') == 1:
                if url and not cover:
                    cover = url
                continue
            if not url:
                continue
            if 'm3u8' in url:
                orig = None
                ext = ''
                if url.endswith('.m3u8/ts.m3u8'):
                    orig = url[:-len('.m3u8/ts.m3u8')]
                    m = re.search(r'\.([A-Za-z0-9]+)$', orig)
                    ext = (m.group(1).upper() if m else '原片')
                videos.append({'m3u8': url, 'orig': orig, 'ext': ext})
            elif re.search(r'\.(mp4|mov|avi|mkv|flv|wmv)$', url, re.I):
                m = re.search(r'\.([A-Za-z0-9]+)$', url)
                videos.append({'m3u8': None, 'orig': url,
                               'ext': (m.group(1).upper() if m else '原片')})
        return videos, cover

    def _vod(self, t):
        if not isinstance(t, dict):
            return None
        tid = str(t.get('tid') or '')
        if not tid:
            return None
        videos, cover = self._videos_of(t)
        if not videos:
            return None
        self._cache[tid] = t
        subject = (t.get('subject') or '').strip()
        views = t.get('views') or ''
        replies = t.get('replies') or ''
        remarks = ''
        if views:
            remarks = '浏览{} '.format(views)
        if replies:
            remarks += '回复{}'.format(replies)
        return {
            'vod_id': tid,
            'vod_name': subject,
            'vod_pic': cover,
            'vod_remarks': remarks.strip(),
            'vod_actor': t.get('author') or '',
            'vod_content': re.sub(r'<[^>]+>', '', str(t.get('message') or ''))[:200],
        }

    def _list_from(self, items):
        out = []
        for t in items or []:
            v = self._vod(t)
            if v:
                out.append(v)
        return out

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in self.CATS],
                'filters': {}}

    def homeVideoContent(self):
        if not self._login():
            return {'list': []}
        items = []
        seen = set()
        for pg in ('1', '2', '3'):
            r = self._api('post.getIndexList', {'page': pg})
            page_items = []
            if isinstance(r, dict) and isinstance(r.get('data'), dict):
                page_items = r['data'].get('list') or []
            for t in page_items:
                tid = str(t.get('tid') or '')
                if tid and tid not in seen:
                    seen.add(tid)
                    items.append(t)
            if not page_items:
                break
        return {'list': self._list_from(items)}

    def categoryContent(self, tid, pg, filter, extend):
        if not self._login():
            return {'list': []}
        if str(tid) == '0':
            r = self._api('post.getIndexList', {'page': str(pg)})
            items = []
            if isinstance(r, dict) and isinstance(r.get('data'), dict):
                items = r['data'].get('list') or []
            return {'list': self._list_from(items), 'page': pg,
                    'pagecount': 9999, 'limit': 20, 'total': 999999}
        r = self._api('postlist.getThreadList', {'fid': str(tid), 'page': str(pg), 'perpage': '100'})
        items, total = [], 0
        if isinstance(r, dict) and isinstance(r.get('data'), dict):
            items = r['data'].get('list') or []
            try:
                total = int(r['data'].get('count') or 0)
            except Exception:
                total = 0
        return {'list': self._list_from(items), 'page': pg,
                'pagecount': 1, 'limit': 100, 'total': total or 999999}

    def detailContent(self, ids):
        tid = str(ids[0])
        t = self._cache.get(tid)
        if t is None and self._login():
            for pg in ('1', '2', '3'):
                r = self._api('post.getIndexList', {'page': pg})
                items = []
                if isinstance(r, dict) and isinstance(r.get('data'), dict):
                    items = r['data'].get('list') or []
                for it in items:
                    if str(it.get('tid') or '') == tid:
                        t = it
                        break
                if t:
                    break
        if t is None:
            return {'list': []}
        videos, cover = self._videos_of(t)
        if not videos:
            return {'list': []}
        self._cache[tid] = t
        plays = []
        for i, v in enumerate(videos):
            if v.get('m3u8'):
                plays.append('视频{}${}'.format(i + 1, v['m3u8']))
            if v.get('orig'):
                plays.append('视频{}-{}${}'.format(i + 1, v.get('ext') or '原片', v['orig']))
        return {'list': [{
            'vod_id': tid,
            'vod_name': (t.get('subject') or '').strip(),
            'vod_pic': cover,
            'vod_actor': t.get('author') or '',
            'vod_remarks': '浏览{} 回复{}'.format(t.get('views') or '', t.get('replies') or ''),
            'vod_content': re.sub(r'<[^>]+>', '', str(t.get('message') or '')),
            'vod_play_from': '妻社',
            'vod_play_url': '#'.join(plays),
        }]}

    def searchContent(self, key, quick, pg):
        if not self._login():
            return {'list': []}
        r = self._api('cearch.search', {'page': str(pg), 'perpage': '10',
                                        'keywords': key, 'isUser': 'false', 'type': 'all'})
        if isinstance(r, dict) and r.get('code') == 200 and isinstance(r.get('data'), dict):
            threads = r['data'].get('threads') or []
            out = self._list_from(threads)
            if out:
                return {'list': out}
        out = []
        for p in ('1', '2', '3'):
            rr = self._api('post.getIndexList', {'page': p})
            items = []
            if isinstance(rr, dict) and isinstance(rr.get('data'), dict):
                items = rr['data'].get('list') or []
            for t in items:
                hay = str(t.get('subject') or '') + str(t.get('message') or '')
                if key in hay:
                    v = self._vod(t)
                    if v:
                        out.append(v)
            if out:
                break
        return {'list': out}

    def playerContent(self, flag, id, vipFlags):
        url = id or ''
        return {'parse': 0, 'url': url,
                'header': {'User-Agent': self.UA,
                           'Referer': 'https://{}/'.format(self._discover_host())}}

    def getName(self):
        return '妻社'

    def _proxy_from(self):
        try:
            name = self.getName()
        except Exception:
            name = ''
        return (name or 'qishe').strip() or 'qishe'

    def _fetch_raw(self, url, timeout=25):
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': self.UA, 'Accept-Encoding': 'gzip'})
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        raw = r.read()
                        enc = (r.headers.get('Content-Encoding') or '').lower()
                except Exception as e:
                    part = getattr(e, 'partial', None)
                    if not part:
                        continue
                    raw = part
                    enc = ''
                if enc == 'gzip':
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                if raw:
                    return raw
            except Exception:
                continue
        return None

    def localProxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if not isinstance(params, dict):
            params = {}
        ptype = params.get('type')
        u = urllib.parse.unquote(str(params.get('u') or ''))
        if not u or '127.0.0.1' in u:
            return [404, 'text/plain', b'']
        if ptype == 'm3u8':
            raw = self._fetch_raw(u)
            if not raw:
                return [404, 'text/plain', b'']
            text = raw.decode('utf-8', 'ignore')
            base = u.rsplit('/', 1)[0] + '/'
            out = []
            for line in text.splitlines():
                s = line.strip()
                if s and not s.startswith('#'):
                    seg = s if (s.startswith('http://') or s.startswith('https://')) \
                        else urllib.parse.urljoin(base, s)
                    out.append('http://127.0.0.1:9978/proxy?do=py&from=%s&type=ts&u=%s'
                               % (urllib.parse.quote(self._proxy_from(), safe=''),
                                  urllib.parse.quote(seg, safe='')))
                else:
                    out.append(line)
            return [200, 'application/vnd.apple.mpegurl',
                    '\n'.join(out).encode('utf-8')]
        if ptype == 'ts':
            data = self._fetch_raw(u)
            if not data:
                return [404, 'text/plain', b'']
            return [200, 'video/mp2t', data]
        return [404, 'text/plain', b'']
