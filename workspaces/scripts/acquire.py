"""Bounded HTTPS acquisition with DNS pinning, redirect checks and byte caching."""
import http.client
import ipaddress
import json
import os
import socket
import ssl
import time
from urllib.parse import urlsplit, urlunsplit, urljoin

from common import DataError, require, sha256, save, now


def public_url(url):
    require(isinstance(url, str) and not any(ord(c) < 33 for c in url), 'invalid_url')
    try:
        p = urlsplit(url)
        require(p.scheme == 'https' and p.hostname and not p.username and not p.password
                and p.port in (None, 443), 'https_public_url_required')
        host = p.hostname.encode('idna').decode('ascii')
    except (ValueError, UnicodeError):
        raise DataError('invalid_url') from None
    require(host != 'localhost' and not host.endswith(('.localhost', '.local', '.internal')), 'private_host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        require(address.is_global and not address.is_multicast and not address.is_unspecified, 'private_address')
    return urlunsplit(('https', p.netloc.lower(), p.path or '/', p.query, ''))


def public_addresses(host):
    addresses = sorted({r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    require(addresses, 'dns_no_addresses')
    for value in addresses:
        ip = ipaddress.ip_address(value)
        require(ip.is_global and not ip.is_multicast and not ip.is_unspecified, 'private_dns_address')
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout, proxy_url=None):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self.address = address
        self.proxy_url = proxy_url

    def connect(self):
        # Connect to the already validated address, while preserving certificate validation and SNI.
        if self.proxy_url:
            proxy = urlsplit(self.proxy_url)
            require(proxy.scheme == 'http' and proxy.hostname and not proxy.username and not proxy.password,
                    'trusted_proxy_must_be_plain_http_connect_without_credentials')
            self.set_tunnel(self.address, 443)
            self.sock = socket.create_connection((proxy.hostname, proxy.port or 80), timeout=self.timeout)
            self._tunnel()
            raw = self.sock
        else:
            raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def https_request(url, *, max_bytes=20_000_000, timeout=25, redirects=4, payload=None, headers=None, proxy_env=None):
    original = public_url(url)
    current = original
    chain = []
    deadline = time.monotonic() + timeout
    for _ in range(redirects + 1):
        current = public_url(current)
        p = urlsplit(current)
        addresses = public_addresses(p.hostname)
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'download_deadline')
        conn = PinnedHTTPS(p.hostname, addresses[0], remaining, os.environ.get(proxy_env) if proxy_env else None)
        try:
            request_headers = {'User-Agent': 'WorkAgentResearch/Stage3', 'Accept-Encoding': 'identity', **(headers or {})}
            conn.request('POST' if payload is not None else 'GET', urlunsplit(('', '', p.path, p.query, '')),
                         body=payload, headers=request_headers)
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                require(payload is None and not headers, 'authenticated_or_post_redirect_forbidden')
                location = response.getheader('Location')
                require(location, 'redirect_without_location')
                target = public_url(urljoin(current, location))
                chain.append({'from': current, 'to': target, 'status': response.status})
                current = target
                continue
            require(response.status == 200, 'http_status:' + str(response.status))
            require(response.getheader('Content-Encoding', 'identity').lower() in ('identity', ''), 'compressed_http_body_not_allowed')
            declared = response.getheader('Content-Length')
            if declared:
                require(declared.isdigit() and int(declared) <= max_bytes, 'download_too_large')
            chunks = []; size = 0
            while True:
                remaining = deadline - time.monotonic()
                require(remaining > 0, 'download_deadline')
                if conn.sock:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(65536, max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                require(size <= max_bytes, 'download_too_large')
            data = b''.join(chunks)
            require(data, 'empty_download')
            if declared:
                require(len(data) == int(declared), 'truncated_download')
            return data, {'original_url': original, 'final_url': current, 'redirects': chain,
                          'mime': response.getheader('Content-Type', '').split(';')[0].strip().lower(),
                          'retrieved_at': now(), 'sha256': sha256(data), 'bytes': len(data)}
        finally:
            conn.close()
    raise DataError('too_many_redirects')


def download(url, cache, limits, offline=False):
    url = public_url(url)
    receipt = cache / 'downloads' / (sha256(url.encode()) + '.json')
    if receipt.exists():
        record = json.loads(receipt.read_text())
        if record.get('status')=='failed':
            raise DataError(record['reason'])
        data = (cache / 'blobs' / record['sha256']).read_bytes()
        require(record['original_url'] == url and sha256(data) == record['sha256'], 'download_cache_corrupt')
        public_url(record['final_url'])
        require(len(data) <= limits['download_bytes'], 'cached_download_too_large')
        return data, record
    require(not offline, 'offline_download_cache_missing')
    errors = []
    for _ in range(limits.get('retries', 0) + 1):
        try:
            data, record = https_request(url, max_bytes=limits['download_bytes'],
                                         timeout=limits['timeout_seconds'], redirects=limits['redirects'],
                                         proxy_env=limits.get('trusted_proxy_env'))
            record['prior_errors'] = errors
            blob = cache / 'blobs' / record['sha256']
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists():
                require(sha256(blob.read_bytes()) == record['sha256'], 'blob_cache_corrupt')
            else:
                blob.write_bytes(data)
            save(receipt, record)
            return data, record
        except (OSError, ValueError, http.client.HTTPException) as exc:
            errors.append(str(exc) if isinstance(exc, DataError) else type(exc).__name__)
    reason='download_failed:' + '|'.join(errors)
    save(receipt,{'status':'failed','original_url':url,'reason':reason,'attempt_errors':errors,'attempted_at':now()})
    raise DataError(reason)
