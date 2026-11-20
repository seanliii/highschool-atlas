"""Private read-only runtime for the frozen /highschool-atlas/ release.

Serves exactly the frozen 14-graph snapshot (7 external + 5 local + mapping/ledger),
the three mapped static assets and two JSON APIs on IPv4 loopback only. There is no
authentication inside this app: the whole route is gated by Caddy basic_auth on the
public host. No credentials, models, workers, cookies or outbound network access.

Usage (on the server, behind the gated reverse proxy):
    python3 atlas_public.py --release-root /srv/highschool-atlas/releases/<id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

SELF_DIR = Path(__file__).resolve().parent
if str(SELF_DIR) not in sys.path:
    sys.path.insert(0, str(SELF_DIR))

from graph_browser import (AtlasError, EXTERNAL_IDS, LOCAL_TITLES, SCHEMA_VERSION,
                           parse_params, restore_frozen_projection)

SERVICE = 'highschool-atlas'
DEFAULT_ORIGIN = 'https://play.vortexsean.com'
DEFAULT_PREFIX = '/highschool-atlas/'
DEFAULT_PORT = 19882
GRAPH_IDS = (*EXTERNAL_IDS, *LOCAL_TITLES)
GRAPH_COUNT = 14
PRIMARY_GRAPHS = 12
PUBLIC_GRAPH_IDS = ('S01', 'S02', 'S03', 'S04', 'S06')
PUBLIC_COUNTS = {'graphs': 5, 'primaryGraphs': 5, 'external': 5, 'local': 0, 'supplementary': 0}
PRIVATE_COUNTS = {'graphs': 14, 'primaryGraphs': 12, 'external': 7, 'local': 5, 'supplementary': 2}
MAX_WORKER_SEMAPHORE = 8
ASSET_FILES = {'graphs.html': 'text/html; charset=utf-8',
               'graphs.js': 'text/javascript; charset=utf-8',
               'graphs.css': 'text/css; charset=utf-8'}
GRAPH_FILE_RE = re.compile(r'^private/graphs/(S0[1-7]|[a-z]+)\.json(?:\.xz)?$')
SHA_RE = re.compile(r'^[a-f0-9]{64}$')
CREDENTIAL_KEY_RE = re.compile(r'password|secret|api[_-]?key|access[_-]?token|authorization|cookie|credential', re.I)
SECURITY_HEADERS = (
    ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                 "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
                                 "base-uri 'none'; form-action 'self'; frame-ancestors 'self'"),
    ('Permissions-Policy', 'fullscreen=(self), camera=(), microphone=(), geolocation=(), payment=()'),
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'same-origin'),
    ('Cache-Control', 'no-store'),
)


class AtlasStartupError(RuntimeError):
    """The release tree failed closed; nothing is served."""


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _reject_credential_fields(value, where='root'):
    if isinstance(value, dict):
        for key, item in value.items():
            if CREDENTIAL_KEY_RE.search(str(key)):
                raise AtlasError('冻结图谱含凭据字段: ' + where + '/' + str(key), 503)
            _reject_credential_fields(item, where + '/' + str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_credential_fields(item, where + '/' + str(index))


def _valid_link_url(url):
    if not isinstance(url, str) or not url:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in url) or '\\' in url or '/Users/' in url:
        return False
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return parsed.scheme == 'https' and parsed.hostname in {'github.com', 'play.vortexsean.com'} and not parsed.username and not parsed.password
    return url.startswith('graphs.html?') or (url.startswith('/') and not url.startswith('//'))


class FrozenGraphs:
    """Manifest-pinned, lazily cached, read-only projection store (max 14 graphs)."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self._startup_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._cache = {}
        self._semaphore = threading.BoundedSemaphore(MAX_WORKER_SEMAPHORE)
        self._entries = {}
        self._read_release()

    # ---------------------------------------------------------------- startup
    def _read_json(self, relative):
        path = self.root / relative
        if path.is_symlink() or not path.is_file():
            raise AtlasStartupError('发行登记缺失或为符号链接: ' + relative)
        try:
            return json.loads(path.read_bytes(), object_pairs_hook=_no_duplicate_keys)
        except ValueError as error:
            raise AtlasStartupError('发行登记JSON无效: ' + relative + ' (' + str(error) + ')') from None

    def _read_release(self):
        manifest = self._read_json('manifest.json')
        required = {'schemaVersion', 'service', 'releaseId', 'generatedAt', 'origin', 'prefix',
                    'scope', 'counts', 'stats', 'files', 'deploy', 'frontend', 'runtime', 'omissions'}
        if not isinstance(manifest, dict) or set(manifest) != required or manifest['schemaVersion'] != 1 \
                or manifest['service'] != SERVICE:
            raise AtlasStartupError('发行manifest结构无效')
        if manifest['prefix'] != DEFAULT_PREFIX:
            raise AtlasStartupError('发行prefix必须为 ' + DEFAULT_PREFIX)
        if urlsplit(manifest['origin']).hostname not in {'play.vortexsean.com', '127.0.0.1', 'localhost'}:
            raise AtlasStartupError('发行origin未登记')
        counts = manifest['counts']
        self.public_mode = counts == PUBLIC_COUNTS
        if counts not in (PRIVATE_COUNTS, PUBLIC_COUNTS):
            raise AtlasStartupError('发行图数与私人14图或公开5图约定不符')
        scope = manifest['scope']
        if self.public_mode:
            if scope.get('anonymousAccess') is not True or scope.get('publicRedistributionAllowed') is not True \
                    or scope.get('gateRequired') or scope.get('privateGrant') or scope.get('liveOnly'):
                raise AtlasStartupError('公开版权利边界与匿名访问约定不符')
        elif not scope.get('privateGrant') or scope.get('publicRedistributionAllowed') or scope.get('anonymousAccess') \
                or not scope.get('gateRequired') or scope.get('liveOnly'):
            raise AtlasStartupError('发行权利边界未按私人非商业只读登记')
        self.release = manifest
        self.release_id = manifest['releaseId']
        self.graph_count = counts['graphs']
        self.primary_graphs = counts['primaryGraphs']
        self.graph_ids = PUBLIC_GRAPH_IDS if self.public_mode else GRAPH_IDS

        graph_manifest = self._read_json('graph_manifest.json')
        graph_required = {'schemaVersion', 'service', 'generatedAt', 'catalogVersion', 'notice', 'graphs', 'counts'}
        if not isinstance(graph_manifest, dict) or set(graph_manifest) != graph_required \
                or graph_manifest['schemaVersion'] != 1 or graph_manifest['service'] != SERVICE:
            raise AtlasStartupError('图谱manifest结构无效')
        graphs = graph_manifest['graphs']
        if not isinstance(graphs, list) or len(graphs) != self.graph_count:
            raise AtlasStartupError('图谱manifest数量与发行模式不符')
        if [g['id'] for g in graphs] != list(self.graph_ids):
            raise AtlasStartupError('图谱manifest顺序或ID与发行模式不符')
        families = {'external': 0, 'local': 0, 'supplementary': 0}
        for entry in graphs:
            fields = {'id', 'file', 'sha256', 'bytes', 'nodeCount', 'edgeCount', 'title',
                      'subtitle', 'family', 'boundary', 'version', 'meta'}
            if set(entry) - {'uncompressedSha256', 'uncompressed_sha256'} != fields:
                raise AtlasStartupError('图谱登记缺少必需字段: ' + str(entry.get('id')))
            if not isinstance(entry, dict) or set(entry) - {'uncompressedSha256', 'uncompressed_sha256'} != fields or entry['family'] not in families:
                raise AtlasStartupError('图谱登记字段无效: ' + str(entry.get('id')))
            if entry['file'] != 'private/graphs/' + entry['id'] + ('.json.xz' if entry['file'].endswith('.xz') else '.json') or not GRAPH_FILE_RE.match(entry['file']):
                raise AtlasStartupError('图谱文件名不在白名单: ' + entry['file'])
            if not SHA_RE.match(entry['sha256']) or type(entry['bytes']) is not int or entry['bytes'] <= 0:
                raise AtlasStartupError('图谱登记哈希或大小无效: ' + entry['id'])
            if type(entry['nodeCount']) is not int or type(entry['edgeCount']) is not int \
                    or entry['nodeCount'] < 0 or entry['edgeCount'] < 0:
                raise AtlasStartupError('图谱登记计数无效: ' + entry['id'])
            if entry['nodeCount'] == 0:
                raise AtlasStartupError('图谱为空: ' + entry['id'])
            families[entry['family']] += 1
            self._entries[entry['id']] = entry
        expected_families = {'external': counts['external'], 'local': counts['local'], 'supplementary': counts['supplementary']}
        if families != expected_families:
            raise AtlasStartupError('图谱族计数与发行模式不符')
        self.graph_manifest = graph_manifest

        private = self.root / 'private' / 'graphs'
        self.compressed = any(entry['file'].endswith('.xz') for entry in graphs)
        actual = {p.name for p in private.iterdir() if p.is_file() or p.is_symlink()}
        suffix = '.xz' if self.compressed else ''
        expected = {entry['id'] + '.json' + suffix for entry in graphs}
        if actual != expected:
            raise AtlasStartupError('private/graphs 存在未登记或多余文件: ' + ','.join(sorted(actual ^ expected)))
        public = self.root / 'public'
        if not public.is_dir():
            raise AtlasStartupError('public 目录缺失')
        for name in ASSET_FILES:
            if not (public / name).is_file() or (public / name).is_symlink():
                raise AtlasStartupError('public 资产缺失: ' + name)
        if {p.name for p in public.iterdir()} != set(ASSET_FILES):
            raise AtlasStartupError('public 目录只能包含映射的三个静态资产')

        files = manifest['files']
        for name in [*ASSET_FILES, *(e['file'] for e in graphs)]:
            if 'public/' + name not in files and name not in files:
                raise AtlasStartupError('manifest缺少文件登记: ' + name)

        # Startup integrity pass: hash every pinned graph file before serving anything.
        for entry in graphs:
            path = self.root / entry['file']
            if path.is_symlink() or not path.is_file():
                raise AtlasStartupError('图谱文件缺失或为符号链接: ' + entry['file'])
            data = self._read_graph_bytes(path, entry, startup=True)
            del data

    # ---------------------------------------------------------------- serving
    def _read_graph_bytes(self, path, entry, *, startup=False):
        error = AtlasStartupError if startup else AtlasError
        if path.is_symlink() or not path.is_file():
            raise error('图谱文件缺失或为符号链接: ' + entry['file'])
        data = path.read_bytes()
        if len(data) != entry['bytes']:
            raise error('图谱文件大小与登记不符: ' + entry['id'])
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise error('图谱文件与登记SHA-256失配: ' + entry['id'])
        if self.compressed:
            try:
                data = lzma.decompress(data)
            except lzma.LZMAError:
                raise error('压缩图谱无法还原: ' + entry['id']) from None
            expected = entry.get('uncompressedSha256', entry.get('uncompressed_sha256'))
            if not expected or hashlib.sha256(data).hexdigest() != expected:
                raise error('压缩图谱还原后与登记SHA-256失配: ' + entry['id'])
        return data

    def catalog(self, query=''):
        parse_params(query, catalog=True)
        graphs = []
        for entry in self.graph_manifest['graphs']:
            row = {'id': entry['id'], 'title': entry['title'], 'subtitle': entry['subtitle'],
                   'family': entry['family'], 'nodeCount': entry['nodeCount'], 'edgeCount': entry['edgeCount'],
                   'boundary': entry['boundary'], 'version': entry['version'], 'meta': entry['meta']}
            if entry['family'] == 'external':
                row['sourceName'] = entry['title']
            graphs.append(row)
        counts = {'external': self.release['counts']['external'], 'local': self.release['counts']['local'],
                  'browsable': self.primary_graphs, 'supplementary': self.release['counts']['supplementary']}
        return {'schemaVersion': SCHEMA_VERSION, 'version': self.graph_manifest['catalogVersion'],
                'generatedAt': self.graph_manifest['generatedAt'], 'counts': counts,
                'graphs': graphs, 'notice': self.graph_manifest['notice'],
                'scope': {'anonymousAccess': self.public_mode,
                          'sourceLicensing': self.release['scope'].get('sourceLicensing', ''),
                          'repository': 'https://github.com/seanliii/highschool-atlas' if self.public_mode else None}}

    def browse(self, query=''):
        params = parse_params(query)
        with self._semaphore:
            graph = self._load(params['graph'])
            return graph.browse(params)
    def health(self):
        return {'service': SERVICE, 'releaseId': self.release_id, 'graphs': self.graph_count,
                'primaryGraphs': self.primary_graphs, 'restrictedData': not self.public_mode, 'readOnly': True}

    def _load(self, graph_id):
        with self._load_lock:
            if graph_id in self._cache:
                return self._cache[graph_id]
        if graph_id not in self._entries:
            raise AtlasError('当前发行模式未登记该图谱', 404)
        entry = self._entries[graph_id]
        path = self.root / entry['file']
        if path.is_symlink() or not path.is_file():
            raise AtlasError('冻结图谱文件不可用', 503)
        data = self._read_graph_bytes(path, entry)
        try:
            document = json.loads(data, object_pairs_hook=_no_duplicate_keys)
        except ValueError:
            raise AtlasError('冻结图谱JSON无效', 503) from None
        graph = restore_frozen_projection(document)
        if graph.id != graph_id:
            raise AtlasError('冻结图谱ID与登记不符', 503)
        if len(graph.nodes) != entry['nodeCount'] or len(graph.edges) != entry['edgeCount']:
            raise AtlasError('冻结图谱计数与登记不符', 503)
        if len(document['nodes']) != entry['nodeCount'] \
                or len({row['id'] for row in document['nodes']}) != entry['nodeCount']:
            raise AtlasError('冻结图谱存在重复节点ID或计数不符', 503)
        blob = json.dumps(document, ensure_ascii=False)
        if '/Users/' in blob:
            raise AtlasError('冻结图谱包含本机路径，拒绝服务', 503)
        _reject_credential_fields(document, graph_id)
        for row in document['nodes']:
            links = row.get('links') or []
            if not isinstance(links, list):
                raise AtlasError('冻结图谱链接结构不合法', 503)
            for link in links:
                if not isinstance(link, dict) or set(link) - {'label', 'url', 'available', 'reason'} \
                        or not _valid_link_url(link.get('url')) \
                        or ('available' in link and type(link.get('available')) is not bool):
                    raise AtlasError('冻结图谱链接结构不合法', 503)
        with self._load_lock:
            self._cache[graph_id] = graph
            if len(self._cache) > GRAPH_COUNT:
                self._cache.clear()
                self._cache[graph_id] = graph
        return graph


class AtlasHandler(BaseHTTPRequestHandler):
    """GET/HEAD-only gate in front of FrozenGraphs. Origin/Host must match the gated site."""
    server_version = 'HighschoolAtlas/1'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    runtime = None
    allowed_host = urlsplit(DEFAULT_ORIGIN).hostname
    prefix = DEFAULT_PREFIX

    def log_message(self, _format, *_args):
        pass

    def log_request(self, code='-', _size='-'):
        # Route only: never the query string, headers or client identity.
        print('[atlas] %s %s %s' % (self.command, code, urlsplit(self.path).path), flush=True)

    # ---------------------------------------------------------------- helpers
    def _origin_allowed(self):
        hosts = self.headers.get_all('Host') or []
        if len(hosts) != 1 or hosts[0] != self.allowed_host:
            return False
        origins = self.headers.get_all('Origin') or []
        if len(origins) > 1:
            return False
        if origins and origins[0] != 'https://' + self.allowed_host.split(':', 1)[0]:
            return False
        return (self.headers.get_all('Sec-Fetch-Site') or []) != ['cross-site']

    def _route(self):
        if len(self.path) > 16384 or re.search(r'%(?![0-9a-fA-F]{2})', self.path):
            return None
        parsed = urlsplit(self.path)
        path = parsed.path
        if parsed.scheme or parsed.netloc or parsed.fragment or any(ord(c) < 32 or ord(c) == 127 for c in path) or '\\' in path:
            return None
        if path == self.prefix.rstrip('/'):
            return ('redirect-root',)
        if not path.startswith(self.prefix):
            return None
        rest = path[len(self.prefix):]
        if rest == '':
            return ('redirect-root',)
        if rest.startswith('api/atlas/'):
            return ('api', rest[len('api/atlas/'):])
        if rest in ASSET_FILES:
            return ('asset', rest)
        if rest == 'health':
            return ('health',)
        return None

    def _send(self, status, body=b'', content_type='application/json; charset=utf-8', extra=()):
        self.send_response(status)
        if content_type:
            self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for name, value in (*SECURITY_HEADERS, *extra):
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD' and body:
            self.wfile.write(body)

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode())

    def _forbidden(self):
        self._json(403, {'error': '私人图谱入口仅限登记站点同源访问'})

    # ---------------------------------------------------------------- verbs
    def do_GET(self):
        self._dispatch('GET')

    def do_HEAD(self):
        self._dispatch('HEAD')

    def do_POST(self):
        if not self._origin_allowed():
            return self._forbidden()
        route = self._route()
        if route is None:
            return self._json(404, {'error': '入口不存在'})
        self.close_connection = True
        return self._json(405, {'error': '只接受GET/HEAD，POST被拒绝'})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def _dispatch(self, method):
        if not self._origin_allowed():
            return self._forbidden()
        route = self._route()
        if route is None:
            return self._json(404, {'error': '入口不存在'})
        kind, name = route[0], (route[1] if len(route) > 1 else None)
        if kind == 'redirect-root':
            query = urlsplit(self.path).query
            location = self.prefix + 'graphs.html' + ('?' + query if query else '')
            return self._send(302, b'', content_type=None, extra=[('Location', location)])
        if kind == 'health':
            return self._json(200, self.runtime.health())
        if kind == 'asset':
            if method == 'HEAD' or method == 'GET':
                return self._asset(name)
            return self._json(405, {'error': '静态资产只接受GET/HEAD'})
        # API endpoints: GET only.
        if method != 'GET':
            return self._json(405, {'error': '图谱接口只接受GET'})
        if name == 'catalog':
            return self._api(self.runtime.catalog)
        if name == 'browse':
            return self._api(self.runtime.browse)
        return self._json(404, {'error': '图谱入口不存在'})

    def _api(self, call):
        query = urlsplit(self.path).query
        try:
            return self._json(200, call(query))
        except AtlasError as error:
            return self._json(error.http_status, {'error': str(error)})
        except Exception:
            return self._json(503, {'error': '冻结图谱暂不可用；未修改任何记录'})

    def _asset(self, name):
        path = self.runtime.root / 'public' / name
        registered = self.runtime.release['files'].get('public/' + name, {}).get('sha256')
        try:
            data = path.read_bytes()
        except OSError:
            return self._json(404, {'error': '静态资产不可用'})
        if not registered or hashlib.sha256(data).hexdigest() != registered:
            return self._json(503, {'error': '静态资产与发行登记失配'})
        self._send(200, data, content_type=ASSET_FILES[name])


def serve(release_root, *, host='127.0.0.1', port=DEFAULT_PORT, allowed_host=None):
    """Start the loopback-only server. Never binds a public interface."""
    if host != '127.0.0.1':
        raise ValueError('图谱后端只绑定IPv4回环，公网由口令保护代理提供')
    runtime = FrozenGraphs(release_root)
    AtlasHandler.runtime = runtime
    AtlasHandler.allowed_host = allowed_host or urlsplit(runtime.release['origin']).hostname
    AtlasHandler.prefix = runtime.release['prefix']
    httpd = ThreadingHTTPServer((host, port), AtlasHandler)
    httpd.daemon_threads = True
    health = runtime.health()
    print('[atlas] serving release %s on http://%s:%d%s (gate: %s)' % (
        health['releaseId'], host, httpd.server_address[1], AtlasHandler.prefix,
        runtime.release['scope']['gateRequired']), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private read-only frozen atlas runtime (loopback only).')
    parser.add_argument('--release-root', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--allowed-host', default=None,
                        help='Exact Host header required (default: origin host). Local checks may override.')
    parser.add_argument('--check-only', action='store_true', help='Validate the release tree and exit.')
    args = parser.parse_args(argv)
    if args.host not in {'127.0.0.1', 'localhost'}:
        parser.error('只允许IPv4回环地址；公网由反向代理负责')
    if args.check_only:
        runtime = FrozenGraphs(args.release_root)
        print(json.dumps(runtime.health(), ensure_ascii=False))
        catalog = runtime.catalog()
        print('[atlas] graphs=%d primary=%d browsable=%d' % (
            len(catalog['graphs']), catalog['counts']['browsable'], catalog['counts']['browsable']))
        return 0
    serve(args.release_root, host=args.host, port=args.port, allowed_host=args.allowed_host)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
