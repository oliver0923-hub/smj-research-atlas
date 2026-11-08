"""Bounded OA network access: DNS pinning, redirect checks and host backoff."""
import ipaddress
import socket
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpcore
import httpx

AGENT = 'SMJResearchAtlas/4.0 (Open Access research evidence; bounded crawler)'
MAX_BYTES = 25_000_000


class PolicyError(ValueError):
    pass


def addresses(host, port=443, resolver=None):
    resolver = resolver or socket.getaddrinfo
    results = resolver(host, port, type=socket.SOCK_STREAM)
    ips = list(dict.fromkeys(r[4][0] for r in results))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise PolicyError('ssrf_nonpublic_dns')
    return ips


def check_url(url, resolver=None):
    try:
        p = urlparse(url)
        if (p.scheme != 'https' or not p.hostname or p.username or p.password
                or p.port not in (None, 443) or len(url) > 4096
                or p.hostname.lower().endswith(('.local', '.internal', '.localhost'))
                or p.hostname.lower() in {'localhost', 'metadata.google.internal'}):
            raise PolicyError('ssrf_unsafe_url')
        addresses(p.hostname, resolver=resolver)
        return p
    except (ValueError, UnicodeError) as exc:
        raise PolicyError('ssrf_unsafe_url') from exc


class PublicBackend(httpcore.SyncBackend):
    """Connect to an already checked IP; TLS SNI remains the original hostname.

    Pinning at connect_tcp avoids a second DNS resolution/rebinding race.
    HTTPX/httpcore's backend adapter is pinned and covered by regression tests.
    """
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        host = host.decode() if isinstance(host, bytes) else host
        ips = addresses(host, port)
        last = None
        for ip in ips:
            try:
                return super().connect_tcp(ip, port, timeout, local_address, socket_options)
            except (OSError, httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise last


def public_client():
    transport = httpx.HTTPTransport(retries=0, trust_env=False)
    transport._pool._network_backend = PublicBackend()
    return httpx.Client(transport=transport, timeout=20, follow_redirects=False,
                        trust_env=False, headers={'User-Agent': AGENT})


def retry_seconds(value, clock=None):
    clock = clock or datetime.now(timezone.utc)
    try:
        return max(1, min(86400, int(value)))
    except (ValueError, TypeError):
        try:
            return max(1, min(86400, int((parsedate_to_datetime(value)-clock).total_seconds())))
        except (ValueError, TypeError, OverflowError):
            return 300


class OAFetcher:
    def __init__(self, client=None, resolver=None, interval=0.6, sleep=time.sleep, clock=time.monotonic):
        self.client = client or public_client()
        self.resolver = resolver
        self.interval, self.sleep, self.clock = interval, sleep, clock
        self.host_times, self.robots, self.cooldowns = {}, {}, {}
        self.requests = 0
        self.max_requests = 100000

    def _request(self, url):
        if self.requests >= self.max_requests:raise PolicyError('global_request_budget')
        p = check_url(url, self.resolver)
        host = p.hostname
        if self.cooldowns.get(host, 0) > self.clock():
            raise PolicyError('host_retry_after')
        delay = self.interval-(self.clock()-self.host_times.get(host, -100000))
        if delay > 0:
            self.sleep(delay)
        self.host_times[host] = self.clock()
        self.requests += 1
        with self.client.stream('GET', url) as response:
            if response.status_code == 429:
                self.cooldowns[host] = self.clock()+retry_seconds(response.headers.get('retry-after'))
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise PolicyError('document_budget_exceeded')
                chunks.append(chunk)
            headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-encoding','content-length'}}
            return httpx.Response(response.status_code, headers=headers,
                                  content=b''.join(chunks), request=response.request)

    def allowed(self, url):
        p = check_url(url, self.resolver)
        key = p.hostname
        if key not in self.robots:
            response, _ = self.fetch('https://'+p.netloc+'/robots.txt', policy=False)
            if response.status_code == 404:
                self.robots[key] = True
            elif response.status_code == 200:
                robot = RobotFileParser()
                robot.parse(response.text.splitlines())
                self.robots[key] = robot
            elif response.status_code == 429:
                raise PolicyError('host_retry_after')
            else:
                raise PolicyError('robots_unavailable_http_'+str(response.status_code))
        rule = self.robots[key]
        return rule if isinstance(rule, bool) else rule.can_fetch(AGENT, url)

    def fetch(self, url, policy=True):
        chain = []
        for _ in range(6):
            check_url(url, self.resolver)
            if url in chain:
                raise PolicyError('redirect_loop')
            if policy and not self.allowed(url):
                raise PolicyError('robots_disallowed')
            chain.append(url)
            response = self._request(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get('location', ''))
                continue
            return response, chain
        raise PolicyError('redirect_budget_exceeded')

    def close(self):
        self.client.close()
