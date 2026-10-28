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
    """An S3 request that failed, with the HTTP status and S3's error code.

    Attributes:
        status: The HTTP status, or 0 when the request was never sent.
        code: S3's error code, such as NoSuchBucket; empty when the response had none.
    """

    def __init__(self, status: int, code: str, message: str):
        """Build the error and its message.

        Args:
            status: The HTTP status, or 0 when the request was never sent.
            code: S3's error code, or an empty string.
            message: S3's error message, or a description of what failed.
        """
        super().__init__(f"HTTP {status} {code}: {message}".strip())
        self.status, self.code = status, code


# --- the endpoint -----------------------------------------------------------------------------


def is_local_host(host: str) -> bool:
    """Tell whether a host is on this machine or a private network.

    Args:
        host: A host name or IP address.

    Returns:
        True when every address the host resolves to is loopback, private or link-local;
        False when any isn't, or when the name doesn't resolve.
    """
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
    """Tell whether an ipaddress address is loopback, private or link-local."""
    return ip.is_loopback or ip.is_private or ip.is_link_local


def check_endpoint(endpoint: str) -> str:
    """Check an endpoint URL and return it without a trailing slash.

    Plain http is refused to anything that isn't local or private, since the rulings and the keys
    would cross the internet unencrypted.

    Args:
        endpoint: The S3 endpoint URL.

    Returns:
        The endpoint without a trailing slash.

    Raises:
        ValueError: When it isn't an http(s) URL, or is plain http to a public host.
    """
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"not an http(s) URL: {endpoint!r}")
    if parsed.scheme == "http" and not is_local_host(parsed.hostname):
        raise ValueError(f"{parsed.hostname} isn't on this machine or a private network, so it needs https://, "
                         "not http://: the rulings and your keys would cross the internet unencrypted")
    return endpoint.rstrip("/")


def credentials(profile: str | None = None) -> tuple[str, str] | None:
    """Find the S3 keys: from the environment, or else from a profile in ~/.aws/credentials.

    Keys never come from config.json.

    Args:
        profile: The credentials profile to read; defaults to AWS_PROFILE, then "default".

    Returns:
        (access key, secret key), or None when neither place has both.
    """
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
    """HMAC-SHA256 of text under key, as raw bytes."""
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def _quote(text: str, safe: str = "-_.~") -> str:
    """Percent-encode text the way Signature Version 4 expects: everything but the unreserved characters."""
    return urllib.parse.quote(text, safe=safe)


def sign(method: str, host: str, path: str, query: dict, headers: dict, payload_hash: str,
         access_key: str, secret_key: str, region: str, now: datetime) -> dict:
    """Sign a request with AWS Signature Version 4 (the S3 header form).

    Args:
        method: The HTTP method.
        host: The Host header the request will be sent with.
        path: The request path, not yet percent-encoded.
        query: The query parameters.
        headers: Extra headers to sign along with the ones this adds.
        payload_hash: The hex SHA-256 of the request body.
        access_key: The S3 access key.
        secret_key: The S3 secret key.
        region: The region in the signing scope.
        now: The signing time, in UTC.

    Returns:
        The headers to send, lower-cased, including host, x-amz-date, x-amz-content-sha256 and authorization.
    """
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
    """A client for one bucket on an S3-compatible server."""

    def __init__(self, endpoint: str, bucket: str, access_key: str | None, secret_key: str | None,
                 region: str = "us-east-1", addressing: str = "path", timeout: float = 60):
        """Set up the client; nothing is sent until the first request.

        Args:
            endpoint: The server's URL, checked by check_endpoint().
            bucket: The bucket name.
            access_key: The access key, or None for a client that can only make unsigned requests.
            secret_key: The secret key, or None.
            region: The region to sign for.
            addressing: "path" for host/bucket/key URLs, "virtual" for bucket.host/key.
            timeout: Seconds to wait for the server on each request.

        Raises:
            ValueError: When the endpoint fails check_endpoint().
        """
        self.endpoint, self.bucket = check_endpoint(endpoint), bucket
        self.access_key, self.secret_key = access_key, secret_key
        self.region, self.addressing, self.timeout = region, addressing, timeout

    def _url(self, key: str) -> tuple[str, str, str]:
        """Build (scheme://host, Host header, path) for a key, path-style or virtual-hosted."""
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
        """Send one request to the bucket.

        An error status is returned, not raised, so callers can treat 404 as an answer.

        Args:
            method: The HTTP method.
            key: The object key; empty for the bucket itself.
            query: Query parameters.
            body: The request body; sent only for PUT and POST.
            headers: Extra headers.
            signed: Whether to sign the request; False to see what anyone without keys gets.

        Returns:
            (status, headers with lower-cased names, body).

        Raises:
            S3Error: When the request must be signed and there are no keys.
            urllib.error.URLError: When the server can't be reached.
        """
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
        """Turn an error response into an S3Error, using its XML Code and Message when it has them."""
        try:
            root = ET.fromstring(body)
            return S3Error(status, root.findtext("Code") or "", root.findtext("Message") or "")
        except ET.ParseError:
            return S3Error(status, "", body[:200].decode("utf-8", "replace"))

    def get(self, key: str) -> bytes | None:
        """Read an object.

        Args:
            key: The object key.

        Returns:
            The object's bytes, or None when there's no such object.

        Raises:
            S3Error: For any other failure.
        """
        status, _, body = self.request("GET", key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body)
        return body

    def put(self, key: str, data: bytes) -> str:
        """Write an object, replacing any already there.

        Args:
            key: The object key.
            data: The object's bytes.

        Returns:
            The new object's ETag, or an empty string if the server sent none.

        Raises:
            S3Error: When the write fails.
        """
        status, headers, body = self.request("PUT", key, body=data)
        if status != 200:
            raise self._error(status, body)
        return headers.get("etag", "")

    def head(self, key: str) -> dict | None:
        """Read an object's headers without its body.

        Args:
            key: The object key.

        Returns:
            The headers, with lower-cased names, or None when there's no such object.

        Raises:
            S3Error: For any other failure. A HEAD response has no body, so it carries no S3 error code.
        """
        status, headers, body = self.request("HEAD", key)
        if status == 404:
            return None
        if status != 200:
            raise S3Error(status, "", f"HEAD {key}")
        return headers

    def keys(self, prefix: str = "") -> list[dict]:
        """List every key under prefix, with its ETag and size, following continuation tokens.

        Args:
            prefix: The key prefix; empty for the whole bucket.

        Returns:
            One dict per object, with "key", "etag" and "size".

        Raises:
            S3Error: When a listing request fails.
        """
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
        """Tell whether the bucket exists.

        Raises:
            S3Error: For any answer other than 200 or 404, such as 403 for keys without access.
        """
        status, _, body = self.request("HEAD")
        if status in (200, 404):
            return status == 200
        raise S3Error(status, "", "HEAD bucket")

    def create_bucket(self) -> None:
        """Create the bucket.

        Raises:
            S3Error: When the server refuses, including when the bucket already exists.
        """
        status, _, body = self.request("PUT")
        if status != 200:
            raise self._error(status, body)

    def anonymous_access(self, key: str | None = None) -> list[str]:
        """Find what someone without keys can do; an empty list means the bucket is private.

        Args:
            key: An object to try reading too, or None to check only listing.

        Returns:
            A description of each thing an unsigned request could do.
        """
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
        """Return the Server header, if the endpoint sends one."""
        _, headers, _ = self.request("HEAD", signed=False)
        return headers.get("server")
