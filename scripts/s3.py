#!/usr/bin/env python3
"""A small S3 client for the skill's optional RustFS store, using only the standard library.

It signs requests with AWS Signature Version 4 and needs only a handful of calls: GET, PUT and HEAD of an
object, listing keys under a prefix, and checking or creating the bucket. RustFS is the server it's tested
against; any S3-compatible server should work.

judge.py uses it for `sync`; it has no command line of its own.
"""

import configparser
import hashlib
import hmac
import ipaddress
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
UA = "bishop-and-barrister/1.0"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class S3Error(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"HTTP {status} {code}: {message}".strip())
        self.status, self.code = status, code


# --- the endpoint -----------------------------------------------------------------------------


def is_local_host(host: str) -> bool:
    """True when every address the host resolves to is loopback or on a private network."""
    if host.lower() == "localhost":
        return True
    try:
        return _private(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(_private(ipaddress.ip_address(a.split("%")[0])) for a in addresses)


def _private(ip) -> bool:
    return ip.is_loopback or ip.is_private or ip.is_link_local


def check_endpoint(endpoint: str) -> str:
    """The endpoint without a trailing slash; refuses plain http to anything that isn't local or private."""
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"not an http(s) URL: {endpoint!r}")
    if parsed.scheme == "http" and not is_local_host(parsed.hostname):
        raise ValueError(f"{parsed.hostname} isn't on this machine or a private network, so it needs https://, "
                         "not http://: the rulings and your keys would cross the internet unencrypted")
    return endpoint.rstrip("/")


def credentials(profile: str | None = None) -> tuple[str, str] | None:
    """Keys from the environment, or else from a profile in ~/.aws/credentials. Never from config.json."""
    key, secret = os.environ.get("BISHOP_AND_BARRISTER_S3_ACCESS_KEY"), os.environ.get("BISHOP_AND_BARRISTER_S3_SECRET_KEY")
    if key and secret:
        return key, secret
    path = Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or Path.home() / ".aws" / "credentials")
    if path.exists():
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        section = profile or os.environ.get("AWS_PROFILE") or "default"
        if parser.has_section(section):
            key, secret = parser[section].get("aws_access_key_id"), parser[section].get("aws_secret_access_key")
            if key and secret:
                return key, secret
    return None


# --- signing ------------------------------------------------------------------------------------


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def _quote(text: str, safe: str = "-_.~") -> str:
    return urllib.parse.quote(text, safe=safe)


def sign(method: str, host: str, path: str, query: dict, headers: dict, payload_hash: str,
         access_key: str, secret_key: str, region: str, now: datetime) -> dict:
    """Headers for a request signed with AWS Signature Version 4 (the S3 header form)."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    headers = {**{k.lower(): str(v).strip() for k, v in headers.items()},
               "host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash}
    signed = sorted(headers)
    canonical = "\n".join([
        method,
        _quote(path, safe="/-_.~"),
        "&".join(f"{_quote(k)}={_quote(str(v))}" for k, v in sorted(query.items())),
        "".join(f"{k}:{headers[k]}\n" for k in signed),
        ";".join(signed),
        payload_hash,
    ])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), day), region), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                                f"SignedHeaders={';'.join(signed)}, Signature={signature}")
    return headers


# --- the client ---------------------------------------------------------------------------------


class S3:
    def __init__(self, endpoint: str, bucket: str, access_key: str | None, secret_key: str | None,
                 region: str = "us-east-1", addressing: str = "path", timeout: float = 60):
        self.endpoint, self.bucket = check_endpoint(endpoint), bucket
        self.access_key, self.secret_key = access_key, secret_key
        self.region, self.addressing, self.timeout = region, addressing, timeout

    def _url(self, key: str) -> tuple[str, str, str]:
        """(scheme://host, Host header, path) for a key, path-style or virtual-hosted."""
        parsed = urllib.parse.urlparse(self.endpoint)
        if self.addressing == "virtual":
            host = f"{self.bucket}.{parsed.netloc}"
            path = parsed.path + "/" + key
        else:
            host = parsed.netloc
            path = f"{parsed.path}/{self.bucket}" + (f"/{key}" if key else "")
        return f"{parsed.scheme}://{host}", host, path or "/"

    def request(self, method: str, key: str = "", query: dict | None = None, body: bytes = b"",
                headers: dict | None = None, signed: bool = True) -> tuple[int, dict, bytes]:
        query = query or {}
        base, host, path = self._url(key)
        headers = dict(headers or {})
        if signed:
            if not (self.access_key and self.secret_key):
                raise S3Error(0, "NoCredentials", "set BISHOP_AND_BARRISTER_S3_ACCESS_KEY and _SECRET_KEY, "
                                                  "or a profile in ~/.aws/credentials")
            headers = sign(method, host, path, query, headers, hashlib.sha256(body).hexdigest(),
                           self.access_key, self.secret_key, self.region, datetime.now(timezone.utc))
        headers["user-agent"] = UA
        url = base + _quote(path, safe="/-_.~")
        if query:
            url += "?" + "&".join(f"{_quote(k)}={_quote(str(v))}" for k, v in sorted(query.items()))
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, method=method,
                                     headers={k: v for k, v in headers.items() if k != "host"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()

    @staticmethod
    def _error(status: int, body: bytes) -> S3Error:
        try:
            root = ET.fromstring(body)
            return S3Error(status, root.findtext("Code") or "", root.findtext("Message") or "")
        except ET.ParseError:
            return S3Error(status, "", body[:200].decode("utf-8", "replace"))

    def get(self, key: str) -> bytes | None:
        status, _, body = self.request("GET", key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body)
        return body

    def put(self, key: str, data: bytes) -> str:
        status, headers, body = self.request("PUT", key, body=data)
        if status != 200:
            raise self._error(status, body)
        return headers.get("etag", "")

    def head(self, key: str) -> dict | None:
        status, headers, body = self.request("HEAD", key)
        if status == 404:
            return None
        if status != 200:
            raise S3Error(status, "", f"HEAD {key}")
        return headers

    def keys(self, prefix: str = "") -> list[dict]:
        """Every key under prefix, with its ETag and size."""
        out, token = [], None
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if token:
                query["continuation-token"] = token
            status, _, body = self.request("GET", query=query)
            if status != 200:
                raise self._error(status, body)
            root = ET.fromstring(body)
            ns = S3_NS if root.tag.startswith(S3_NS) else ""
            for item in root.findall(f"{ns}Contents"):
                out.append({"key": item.findtext(f"{ns}Key"), "etag": item.findtext(f"{ns}ETag"),
                            "size": int(item.findtext(f"{ns}Size") or 0)})
            if root.findtext(f"{ns}IsTruncated") != "true":
                return out
            token = root.findtext(f"{ns}NextContinuationToken")

    def bucket_exists(self) -> bool:
        status, _, body = self.request("HEAD")
        if status in (200, 404):
            return status == 200
        raise S3Error(status, "", "HEAD bucket")

    def create_bucket(self) -> None:
        status, _, body = self.request("PUT")
        if status != 200:
            raise self._error(status, body)

    def anonymous_access(self, key: str | None = None) -> list[str]:
        """What someone without keys can do: an empty list means the bucket is private."""
        found = []
        status, _, _ = self.request("GET", query={"list-type": "2"}, signed=False)
        if status == 200:
            found.append("list the bucket")
        if key:
            status, _, _ = self.request("GET", key, signed=False)
            if status == 200:
                found.append(f"read {key}")
        return found

    def server(self) -> str | None:
        """The Server header, if the endpoint sends one."""
        _, headers, _ = self.request("HEAD", signed=False)
        return headers.get("server")
