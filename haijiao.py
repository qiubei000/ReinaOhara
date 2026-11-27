# -*- coding: utf-8 -*-
# 海角社区

import base64
import concurrent.futures
import gzip
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


# 账号填这里（播放用，不填播不了；也可以在扩展配置里填 token 和 userid）
DEFAULT_TOKEN = ''  # 原文件自带的他人 token 已清空；播放需在本地 ext 里填自己的 token + userId
DEFAULT_USER_ID = ''  # 填你的 x-user-id


class Spider(BaseSpider):
    SITE_NAME = '海角社区'
    HOST = 'https://www.haijiao.com'
    API = 'https://www.haijiao.com/api'
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
    TIMEOUT = 15
    PER_PAGE = 20
    # nodes 接口挂了时的兜底分类（2026-11-26 实站核对）
    FALLBACK_CATS = [
        ('2020', '海角视频'),
        ('900', '短视频专区'),
        ('1001', '收费视频'),
        ('972', '销魂视频'),
        ('2022', '猫咪AV'),
        ('217', '绿帽影视'),
    ]


    def getName(self):
        return self.SITE_NAME

    def init(self, extend=""):
        self.extend = extend or ''
        self._token = DEFAULT_TOKEN
        self._user_id = DEFAULT_USER_ID
        self._nodes_cache = None
        self._cache = {}
        self._txt_cache = {}
        self._parse_extend()

    def __init__(self):
        self.extend = ''
        self._token = DEFAULT_TOKEN
        self._user_id = DEFAULT_USER_ID
        self._nodes_cache = None
        self._cache = {}
        self._txt_cache = {}

    # ── 扩展配置解析：token + userId ────────────────────────
    def _parse_extend(self):
        ext = (self.extend or '').strip()
        if not ext:
            return
        token = ''
        user_id = ''
        # JSON 写法
        if ext.startswith('{'):
            try:
                cfg = json.loads(ext)
                if isinstance(cfg, dict):
                    token = str(cfg.get('token') or cfg.get('x-user-token')
                                or cfg.get('x_user_token') or '')
                    user_id = str(cfg.get('userId') or cfg.get('user_id')
                                  or cfg.get('x-user-id')
                                  or cfg.get('x_user_id') or '')
            except Exception:
                pass
        if not token:
            # key:value / key=value 写法（中英文冒号都认）
            for part in re.split(r'[\n,;]+', ext):
                part = part.strip()
                if not part:
                    continue
                m = re.match(r'(?i)(x-user-token|token|usertoken)\s*[:：=]\s*(.+)$',
                             part)
                if m:
                    token = m.group(2).strip()
                    continue
                m = re.match(r'(?i)(x-user-id|userid|user-id|user_id|uid)'
                             r'\s*[:：=]\s*(.+)$', part)
                if m:
                    user_id = m.group(2).strip()
                    continue
        if not token:
            # 两行裸值：第一行 token，第二行 userId
            lines = [l.strip() for l in re.split(r'[\n,;]+', ext) if l.strip()]
            if len(lines) >= 1:
                token = lines[0]
            if len(lines) >= 2:
                user_id = lines[1]
        if token:
            self._token = token
        if user_id:
            self._user_id = user_id

    # ── 基础请求 ──────────────────────────────────────────
    def _gunzip(self, raw):
        if not raw:
            return b''
        if raw[:2] == b'\x1f\x8b':
            try:
                return gzip.decompress(raw)
            except Exception:
                return raw
        return raw

    def _http(self, method, url, body=None, headers=None, timeout=None):
        timeout = timeout or self.TIMEOUT
        h = {'User-Agent': self.UA,
             'Accept': 'application/json, text/plain, */*',
             'Accept-Encoding': 'gzip',
             'Referer': self.HOST + '/home',
             'pcVer': '2'}
        if headers:
            h.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            h['Content-Type'] = 'application/json'
        # 沙箱 chunked 大响应偶发截断（盒子不受影响）：IncompleteRead
        # 的 partial 常含近完整体；4 次里取最长的那份抢救出来用。
        best = b''
        for _ in range(4):
            try:
                req = urllib.request.Request(url, data=data, headers=h,
                                             method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return self._gunzip(resp.read())
            except Exception as e:
                partial = getattr(e, 'partial', None)
                if partial and len(partial) > len(best):
                    best = partial
                time.sleep(0.5)
        return self._gunzip(best)

    @staticmethod
    def _dec3(data_str):
        """API 信封 data 字段：base64 套三层 → JSON。"""
        d = data_str
        for _ in range(3):
            d = base64.b64decode(d).decode('utf-8')
        return json.loads(d)

    def _api(self, method, path, body=None, headers=None):
        if path.startswith('http'):
            url = path
        else:
            url = self.API + path
        raw = self._http(method, url, body=body, headers=headers)
        if not raw:
            return None
        try:
            env = json.loads(raw.decode('utf-8', 'ignore'))
        except Exception:
            return None
        if not isinstance(env, dict) or not env.get('success'):
            return None
        data = env.get('data')
        if data is None:
            return None
        if isinstance(data, str):
            try:
                return self._dec3(data)
            except Exception:
                return None
        return data

    def _auth_headers(self):
        h = {'X-HJ-Internal': '1'}
        if self._token:
            h['x-user-token'] = self._token
        if self._user_id:
            h['x-user-id'] = str(self._user_id)
        return h

    # ── 分类 ──────────────────────────────────────────────
    def _nodes(self):
        if self._nodes_cache is not None:
            return self._nodes_cache
        nodes = self._api('GET', '/topic/nodes')
        cats = []
        if isinstance(nodes, list):
            for n in nodes:
                if n.get('display') != 1:
                    continue
                nid = n.get('nodeId')
                name = (n.get('name') or '').strip()
                if nid is None or not name:
                    continue
                cats.append((str(nid), name, int(n.get('sortNo') or 0)))
            cats.sort(key=lambda x: x[2])
            cats = [(i, n) for i, n, _ in cats]
        if not cats:
            cats = list(self.FALLBACK_CATS)
        self._nodes_cache = cats
        return cats

    def homeContent(self, filter):
        cats = [('0', '全部')] + self._nodes()
        return {'class': [{'type_id': i, 'type_name': n} for i, n in cats],
                'filters': {}}

    def homeVideoContent(self):
        items, _ = self._search_page(None, 1)
        return {'list': items}

    # ── 列表 ──────────────────────────────────────────────
    @staticmethod
    def _cover(topic):
        atts = topic.get('attachments') or []
        for a in atts:
            if a.get('category') == 'video' and a.get('coverUrl'):
                return a.get('coverUrl')
        for a in atts:
            if a.get('remoteUrl'):
                return a.get('remoteUrl')
        return ''

    def _vod(self, topic):
        # 只保留带视频的帖子：hasVideo 明确为 False 的剔掉，
        # True 或字段缺失的都保留。
        if topic.get('hasVideo') is False:
            return None
        tid = topic.get('topicId')
        if tid is None:
            return None
        title = (topic.get('title') or '').strip()
        if not title:
            return None
        node = topic.get('node') or {}
        remarks = (node.get('name') or '').strip()
        vc = topic.get('viewCount')
        if vc:
            remarks = (remarks + ' · %s浏览' % vc) if remarks else ('%s浏览' % vc)
        return {'vod_id': str(tid),
                'vod_name': title,
                'vod_pic': self._cover(topic),
                'vod_remarks': remarks,
                'vod_actor': ((topic.get('user') or {}).get('nickname') or ''),
                'vod_content': (topic.get('liteContent') or '')[:200]}

    # ── 封面 .txt 解码（NOTES.md §12）──────────────────────
    # 自定义 base64 字母表（站 JS 解码器 A 的构造参数）：位置 4 是 *、
    # 位置 25 是 #、数字段是 1234567890（不是 0123456789）。
    _TXT_B64_CUSTOM = ("ABCD*EFGHIJKLMNOPQRSTUVWX#YZ"
                       "abcdefghijklmnopqrstuvwxyz1234567890")
    _TXT_B64_STD = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    "abcdefghijklmnopqrstuvwxyz0123456789+/")
    _TXT_B64_TRANS = str.maketrans(_TXT_B64_CUSTOM, _TXT_B64_STD)

    @classmethod
    def _txt_b64decode(cls, text):
        """自定义字母表 base64 解码：去掉非法字符后按自定义表翻译再解码。"""
        clean = re.sub(r'[^A-Za-z0-9\*#]', '', text or '')
        if not clean:
            return b''
        std = clean.translate(cls._TXT_B64_TRANS)
        std += '=' * (-len(std) % 4)
        try:
            return base64.b64decode(std)
        except Exception:
            return b''

    def _decode_txt_cover(self, url):
        """封面 .txt 解码：非 .txt 直链原样返回；.txt 文本 → data URI 图片；
        解不出或魔数不对返回 ''。只解缩略图/视频封面（约 17-31KB 文本），
        超过 200KB 的一律不碰（详情全尺寸图可达 5.4MB）。"""
        if not url:
            return ''
        if not url.lower().endswith('.txt'):
            return url
        cache = getattr(self, '_txt_cache', None)
        if cache is None:
            cache = self._txt_cache = {}
        if url in cache:
            return cache[url]
        result = ''
        try:
            raw = self._http('GET', url,
                             headers={'Referer': self.HOST + '/home'})
            if raw and len(raw) < 200 * 1024:
                uri = self._txt_b64decode(
                    raw.decode('utf-8', 'ignore')).decode('utf-8', 'ignore')
                m = re.match(r'\s*data:image/[^;]+;base64,(.*)$', uri, re.S)
                if m:
                    inner = m.group(1).strip()
                    inner += '=' * (-len(inner) % 4)
                    try:
                        img = base64.b64decode(inner)
                    except Exception:
                        img = b''
                    if img[:2] == b'\xff\xd8':
                        mime = 'image/jpeg'
                    elif img[:4] == b'\x89PNG':
                        mime = 'image/png'
                    elif img[:4] == b'GIF8':
                        mime = 'image/gif'
                    else:
                        img = b''
                    if img:
                        result = ('data:%s;base64,%s' % (
                            mime, base64.b64encode(img).decode()))
        except Exception:
            result = ''
        cache[url] = result
        return result

    def _decode_pics(self, items):
        """列表封面并行解码：把以 .txt 结尾的 vod_pic 换成 data URI 图片。"""
        todo = [v for v in items
                if (v.get('vod_pic') or '').lower().endswith('.txt')]
        if not todo:
            return items
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(self._decode_txt_cover,
                                  [v['vod_pic'] for v in todo]))
        for v, r in zip(todo, results):
            v['vod_pic'] = r if r else ''
        return items

    def _fill_page(self, fetch, pg, key=None):
        """拉满一页：从 API 第 start 页起顺拉，最多 8 个 API 页，把过滤后
        的视频项补满 PER_PAGE 条；同页内按 topicId 去重。返回
        (items, last_full)，last_full 表示后面可能还有。
        列表接口偶发短页/空页/失败：每个 API 页失败（None）或短页
        （<20 条）都重试一次；失败重试后仍 None 则跳过该页继续往
        后拉，连续 2 次失败才停；短页重试后仍短也不停，继续往后拉
        满；只有重试后仍空的页才算到底。API 页分两批并行拉（每批
        4 页），比一页页顺拉快得多。游标：同一列表翻页时从上次拉
        到的 API 页之后继续，避免跨页重复；pg==1 时重置游标。"""
        if not hasattr(self, '_fill_cursor'):
            self._fill_cursor = {}
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        key = '' if key is None else str(key)
        if pg <= 1 or key not in self._fill_cursor:
            start = pg if pg >= 1 else 1
        else:
            start = self._fill_cursor[key]
        items, seen = [], set()
        fails = 0
        hit_end = False
        last_api_pg = start - 1
        for batch in range(2):
            if len(items) >= self.PER_PAGE or hit_end:
                break
            pages = list(range(start + batch * 4, start + batch * 4 + 4))
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                results = list(ex.map(lambda p: self._fetch_one(fetch, p), pages))
            for p, data in zip(pages, results):
                last_api_pg = p
                if data is None:
                    fails += 1
                    if fails >= 2:
                        hit_end = True
                        break
                    continue
                fails = 0
                if len(data) == 0:
                    hit_end = True
                    break
                for t in data:
                    v = self._vod(t)
                    if v and v['vod_id'] not in seen:
                        seen.add(v['vod_id'])
                        items.append(v)
                if len(items) >= self.PER_PAGE:
                    break
        self._fill_cursor[key] = last_api_pg + 1
        return self._decode_pics(items[:self.PER_PAGE]), (not hit_end)

    def _fetch_one(self, fetch, p):
        """拉一个 API 页：失败（None）或短页（<20 条）都重试一次，
        重试只取更多数据的那份。返回 list 或 None（重试后仍失败）。"""
        try:
            data = fetch(p)
        except Exception:
            data = None
        if data is None:
            try:
                data = fetch(p)
            except Exception:
                data = None
            return data if isinstance(data, list) else None
        if isinstance(data, list) and len(data) < self.PER_PAGE:
            try:
                retry = fetch(p)
            except Exception:
                retry = None
            if isinstance(retry, list) and len(retry) > len(data):
                data = retry
        return data if isinstance(data, list) else None
    def _search_page(self, node_id, pg):
        def fetch(p):
            if node_id:
                path = '/topic/search?node_id=%s&page=%d' % (node_id, p)
            else:
                path = '/topic/search?page=%d' % p
            return self._api('GET', path)
        return self._fill_page(fetch, pg, 'cat:' + str(node_id))

    def _search_kw(self, key, pg):
        def fetch(p):
            path = '/topic/search?keyword=%s&page=%d' % (
                urllib.parse.quote(key or ''), p)
            return self._api('GET', path)
        return self._fill_page(fetch, pg, 'search:' + str(key))

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid or '0')
        node_id = None if tid == '0' else tid
        items, last_full = self._search_page(node_id, pg)
        pagecount = pg + 1 if last_full else pg
        return {'page': pg, 'pagecount': pagecount,
                'limit': self.PER_PAGE, 'total': 0, 'list': items}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        items, last_full = self._search_kw(key, pg)
        pagecount = pg + 1 if last_full else pg
        return {'page': pg, 'pagecount': pagecount,
                'limit': self.PER_PAGE, 'total': 0, 'list': items}

    # ── 详情 ──────────────────────────────────────────────
    @staticmethod
    def _strip_html(html):
        if not html:
            return ''
        txt = re.sub(r'<[^>]+>', ' ', html)
        txt = re.sub(r'\s+', ' ', txt)
        return txt.strip()

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0]) if ids else ''
        else:
            raw = str(ids or '').split(',')[0].strip()
        if not raw or not raw.isdigit():
            return {'list': []}
        tid = raw
        d = self._api('GET', '/topic/%s' % tid)
        if not isinstance(d, dict):
            return {'list': []}
        title = (d.get('title') or '').strip() or tid
        node = d.get('node') or {}
        atts = d.get('attachments') or []
        pic = ''
        eps = []
        vidx = 0
        for a in atts:
            if a.get('category') != 'video':
                continue
            aid = a.get('id')
            if aid is None:
                continue
            if not pic and a.get('coverUrl'):
                pic = a.get('coverUrl')
            vidx += 1
            eps.append('视频%d$play@@%s@@%s' % (vidx, tid, aid))
        if not pic:
            pic = self._cover(d)
        pic = self._decode_txt_cover(pic)
        remarks = (node.get('name') or '').strip()
        vc = d.get('viewCount')
        if vc:
            remarks = (remarks + ' · %s浏览' % vc) if remarks else ('%s浏览' % vc)
        if not eps:
            remarks = (remarks + '（无视频）') if remarks else '无视频'
        if not self._token:
            remarks = (remarks + '（播放需填 token）') if remarks \
                else '播放需填 token'
        content = self._strip_html(d.get('content') or '')[:800]
        self._cache[tid] = {'title': title, 'pic': pic}
        return {'list': [{'vod_id': tid, 'vod_name': title,
                          'vod_pic': pic, 'vod_remarks': remarks,
                          'vod_actor': ((d.get('user') or {}).get('nickname')
                                        or ''),
                          'vod_content': content,
                          'vod_play_from': '海角',
                          'vod_play_url': '#'.join(eps)}]}

    # ── 播放：B3 取地址 → localProxy 做 B4 ──────────────────
    def _proxy_base(self):
        # 壳子的 localProxy 地址；没有时回退 127.0.0.1:9978（FongMi 默认端口）
        fn = getattr(self, "getProxyUrl", None)
        if callable(fn):
            try:
                base = (fn() or "").strip()
                if base:
                    return base
            except Exception:
                pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')
        m = re.match(r'play@@(\d+)@@(\d+)', raw)
        if not m:
            return {'parse': 0, 'url': ''}
        tid, aid = m.group(1), m.group(2)
        if not self._token:
            return {'parse': 0, 'url': ''}
        try:
            att_id = int(aid)
            topic_id = int(tid)
        except Exception:
            att_id, topic_id = aid, tid
        d = self._api('POST', '/attachment',
                      {"id": att_id, "resource_id": 2174028,  # 免费帖 id，绕付费墙（见头注释）
                       "resource_type": "topic", "line": "normal1"},
                      headers=self._auth_headers())
        remote = ''
        if isinstance(d, dict):
            remote = d.get('remoteUrl') or ''
        if not remote.startswith('http'):
            return {'parse': 0, 'url': ''}
        proxy = (self._proxy_base() + '&from=%s&type=m3u8&u=%s'
                 % (urllib.parse.quote('海角', safe=''),
                    urllib.parse.quote(remote, safe='')))
        header = {'User-Agent': self.UA, 'Referer': self.HOST + '/home'}
        return {'parse': 0, 'url': proxy, 'header': header}

    # ── localProxy：B4 密钥 XOR 恢复 ───────────────────────
    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        ptype = (param.get('type') or '').strip()
        if ptype == 'key':
            # 代理版 KEY：现取 key 文件 + 同名 .jpg secret，XOR 得真 key，
            # 直接回 16 字节，不用 data: URI。
            key_url = urllib.parse.unquote(str(param.get('k') or ''))
            sec_url = urllib.parse.unquote(str(param.get('s') or ''))
            if not key_url.startswith('http') or not sec_url.startswith('http'):
                return [404, 'text/plain', b'']
            key_bytes = self._http('GET', key_url,
                                   headers={'Referer': self.HOST + '/home'})
            sec_raw = self._http('GET', sec_url,
                                 headers={'Referer': self.HOST + '/home'})
            try:
                sec_bytes = base64.b64decode(
                    sec_raw.decode('utf-8', 'ignore').strip())
            except Exception:
                sec_bytes = b''
            if not key_bytes or not sec_bytes:
                return [404, 'text/plain', b'']
            real = bytes(a ^ b for a, b in
                         zip(key_bytes, sec_bytes[:16]))[:16]
            if len(real) != 16:
                return [404, 'text/plain', b'']
            return [200, 'application/octet-stream', real]
        if ptype == 'ts':
            ts_url = urllib.parse.unquote(
                str(param.get('u') or param.get('url') or ''))
            if not ts_url.startswith('http') or ts_url.startswith('http://127.0.0.1'):
                return [404, 'text/plain', b'']
            data = self._http('GET', ts_url,
                              headers={'Referer': self.HOST + '/home'})
            if not data:
                return [404, 'text/plain', b'']
            return [200, 'video/mp2t', data]
        url = param.get('u') or param.get('url') or param.get('src') or ''
        url = urllib.parse.unquote(str(url))
        if not url.startswith('http') or url.startswith('http://127.0.0.1'):
            return [404, 'text/plain', b'']
        body = self._http('GET', url, headers={'Referer': self.HOST + '/home'})
        if not body:
            return [404, 'text/plain', b'']
        try:
            text = body.decode('utf-8', 'ignore')
        except Exception:
            return [404, 'text/plain', b'']
        if '#EXTM3U' not in text:
            return [404, 'text/plain', b'']
        out = self._b4(text, url)
        if out is None:
            return [404, 'text/plain', b'']
        return [200, 'application/vnd.apple.mpegurl',
                out.encode('utf-8', 'ignore')]

    def _b4(self, m3u8_text, m3u8_url):
        """B4（代理版）：主清单取最高变体；媒体清单里 KEY URI 改指
        localProxy type=key（取时再 XOR）；分片改指 localProxy type=ts。
        播放器全程只连 127.0.0.1，不直连 CDN、不用 data: URI。失败返回 None。"""
        text = m3u8_text
        if '#EXT-X-STREAM-INF' in text:
            best_url = None
            best_bw = -1
            lines = text.splitlines()
            for i, ln in enumerate(lines):
                if ln.startswith('#EXT-X-STREAM-INF'):
                    bw_m = re.search(r'BANDWIDTH=(\d+)', ln)
                    bw = int(bw_m.group(1)) if bw_m else 0
                    if i + 1 < len(lines):
                        u = lines[i + 1].strip()
                        if u and not u.startswith('#') and bw >= best_bw:
                            best_bw = bw
                            best_url = u
            if not best_url:
                return None
            m3u8_url = urllib.parse.urljoin(m3u8_url, best_url)
            body = self._http('GET', m3u8_url,
                              headers={'Referer': self.HOST + '/home'})
            if not body:
                return None
            text = body.decode('utf-8', 'ignore')
            if '#EXTM3U' not in text:
                return None
        # KEY 处理
        mkey = re.search(r'#EXT-X-KEY:([^\n]+)', text)
        if mkey:
            attrs = dict(re.findall(r'([A-Z-]+)=("[^"]*"|[^,]*)',
                                    mkey.group(1)))
            key_uri = (attrs.get('URI') or '').strip('"')
            if key_uri:
                # 代理版：不取 key、不拼 data: URI。KEY 改指 localProxy
                # type=key，取 key 时 localProxy 再现算 XOR（见 localProxy）。
                key_url = urllib.parse.urljoin(m3u8_url, key_uri)
                secret_url = re.sub(r'\.m3u8(\?.*)?$', '.jpg',
                                    m3u8_url.split('?')[0])
                key_proxy = (self._proxy_base() + '&from=%s'
                             '&type=key&k=%s&s=%s'
                             % (urllib.parse.quote('海角', safe=''),
                                urllib.parse.quote(key_url, safe=''),
                                urllib.parse.quote(secret_url, safe='')))
                new_line = re.sub(
                    r'URI="[^"]*"', 'URI="%s"' % key_proxy,
                    mkey.group(0))
                text = text.replace(mkey.group(0), new_line, 1)
        # 分片相对地址补全
        out_lines = []
        for ln in text.splitlines():
            s = ln.strip()
            if s and not s.startswith('#'):
                # 代理版：分片也走 localProxy（type=ts），播放器只连本机
                abs_seg = urllib.parse.urljoin(m3u8_url, s)
                s = (self._proxy_base() + '&from=%s'
                     '&type=ts&u=%s'
                     % (urllib.parse.quote('海角', safe=''),
                        urllib.parse.quote(abs_seg, safe='')))
            out_lines.append(s)
        return '\n'.join(out_lines) + '\n'
