"""Run a bounded, loopback-only HTTP load check against an isolated Django DB."""

import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPHandler,
    HTTPRedirectHandler,
    Request,
    build_opener,
)


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def build_load_opener(cookie=None, hostname="127.0.0.1"):
    handlers = [NoRedirectHandler(), HTTPHandler()]
    if cookie:
        from http.cookiejar import Cookie

        jar = CookieJar()
        jar.set_cookie(
            Cookie(
                version=0,
                name="sessionid",
                value=cookie,
                port=None,
                port_specified=False,
                domain=hostname,
                domain_specified=False,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )
        handlers.append(HTTPCookieProcessor(jar))
    return build_opener(*handlers)


def get_status(opener, url, timeout=10):
    request = Request(url, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def authenticate_staff(base_url):
    username = os.environ.get("AUDIT_STAFF_USERNAME", "")
    password = os.environ.get("AUDIT_STAFF_PASSWORD", "")
    if not username and not password:
        return ""
    if not username or not password:
        raise RuntimeError(
            "Set both AUDIT_STAFF_USERNAME and AUDIT_STAFF_PASSWORD, or neither."
        )

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    login_url = urljoin(base_url, "/site-management/login/")
    status, body = get_status(opener, login_url)
    if status != 200:
        raise RuntimeError("Could not open the management login page.")
    token_match = re.search(
        rb'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
        body,
    )
    if not token_match:
        raise RuntimeError("Could not find the management login CSRF token.")

    form_data = urlencode(
        {
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": token_match.group(1).decode("ascii"),
        }
    ).encode("ascii")
    request = Request(
        login_url,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener.open(request, timeout=10) as response:
        response_body = response.read()
        if response.status != 200 or b"Welcome," not in response_body:
            raise RuntimeError("The supplied account did not reach the CMS dashboard.")

    session = next(
        (cookie.value for cookie in cookie_jar if cookie.name == "sessionid"),
        "",
    )
    if not session:
        raise RuntimeError("The CMS login did not establish a session.")
    return session


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index] * 1000


def main():
    if "--confirm-isolated-local-db" not in sys.argv:
        raise SystemExit(
            "Refusing to run without --confirm-isolated-local-db; use a disposable local DB."
        )
    sys.argv.remove("--confirm-isolated-local-db")

    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--total", type=int, default=1000)
    args = parser.parse_args()

    parsed_base = urlparse(args.base_url)
    if (
        parsed_base.scheme != "http"
        or parsed_base.hostname not in {"127.0.0.1", "localhost", "::1"}
        or args.total < 36
    ):
        raise SystemExit("Use an HTTP loopback server and at least 36 total requests.")
    base_url = args.base_url.rstrip("/") + "/"
    opener = build_load_opener()

    status, body = get_status(opener, urljoin(base_url, "/api/ai/status/"))
    if status != 200 or json.loads(body).get("enabled") is not False:
        raise SystemExit("AI must be disabled before running this load test.")

    staff_session = authenticate_staff(base_url)
    request_opener = build_load_opener(staff_session, parsed_base.hostname)
    paths = (
        ("/", 350),
        ("/accounts/login/", 150),
        ("/accounts/signup/", 150),
        ("/api/ai/status/", 150),
        ("/jobs/1/", 100),
        ("/site-management/", 95),
        ("/api/ai/jobs/?q=SSC", 5),
    )
    workload = []
    for path, weight in paths:
        workload.extend([path] * (args.total * weight // 1000))
    while len(workload) < args.total:
        workload.append("/")
    workload = workload[: args.total]
    random.Random(20261014).shuffle(workload)

    def hit(path):
        started = time.perf_counter()
        try:
            status_code, _body = get_status(
                request_opener,
                urljoin(base_url, path),
            )
            error = None
        except (TimeoutError, URLError, OSError) as exception:
            status_code = None
            error = type(exception).__name__
        duration = time.perf_counter() - started
        time.sleep(0.015)
        return path.split("?", 1)[0], status_code, duration, error

    all_results = []
    errors = []
    started_all = time.perf_counter()
    cursor = 0
    for concurrency in (1, 10, 25):
        count = min(concurrency, args.total - cursor)
        if count <= 0:
            break
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            stage = list(executor.map(hit, workload[cursor : cursor + count]))
        cursor += count
        all_results.extend(stage)
        stage_latencies = [result[2] for result in stage]
        stage_errors = [
            result for result in stage
            if result[1] is None or result[1] >= 400 or result[3]
        ]
        p95 = percentile(stage_latencies, 95)
        print(
            f"Stage concurrency={concurrency}: requests={count}, "
            f"errors={len(stage_errors)}, p95_ms={p95:.1f}"
        )
        if stage_errors or p95 > 2000:
            raise SystemExit("Safety stop threshold reached; remaining load was not sent.")

    if cursor < args.total:
        with ThreadPoolExecutor(max_workers=10) as executor:
            bulk = list(executor.map(hit, workload[cursor:]))
        all_results.extend(bulk)

    elapsed = time.perf_counter() - started_all
    statuses = {}
    for path, status_code, _duration, error in all_results:
        key = f"{path} HTTP {status_code or error}"
        statuses[key] = statuses.get(key, 0) + 1
        if status_code is None or status_code >= 400 or error:
            errors.append(key)

    latencies = [result[2] for result in all_results]
    print(f"Requests={len(all_results)}; errors={len(errors)}")
    print(
        f"p50_ms={percentile(latencies, 50):.1f}; "
        f"p95_ms={percentile(latencies, 95):.1f}; "
        f"p99_ms={percentile(latencies, 99):.1f}; "
        f"throughput_rps={len(all_results) / max(elapsed, 0.001):.2f}"
    )
    for result, count in sorted(statuses.items()):
        print(f"{result}: {count}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
