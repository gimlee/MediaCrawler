# -*- coding: utf-8 -*-
import asyncio
import logging

import httpx
import config


_request_failed_count = 0
logger = logging.getLogger("MediaCrawler")


class RequestFailureLimitExceeded(RuntimeError):
    pass


def get_request_failed_count() -> int:
    return _request_failed_count


def record_request_failure(context: str = "") -> int:
    global _request_failed_count
    _request_failed_count += 1
    failed_limit = getattr(config, "REQUEST_FAILED_LIMIT", 10)
    logger.warning(
        f"[httpx_util] Request failure count: {_request_failed_count}/{failed_limit}. {context}"
    )
    if _request_failed_count > failed_limit:
        raise RequestFailureLimitExceeded(
            f"Request failures exceeded limit {failed_limit}. Last failure: {context}"
        )
    return _request_failed_count


def make_async_client(**kwargs) -> httpx.AsyncClient:
    """创建统一配置的 httpx.AsyncClient。

    从配置文件读取 DISABLE_SSL_VERIFY（默认 False，即开启 SSL 验证）。
    仅在使用企业代理、Burp、mitmproxy 等中间人代理时才需将其设为 True。
    """
    kwargs.setdefault("verify", not getattr(config, "DISABLE_SSL_VERIFY", False))
    return httpx.AsyncClient(**kwargs)


async def request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    retry_times = max(1, int(getattr(config, "REQUEST_RETRY_TIMES", 3)))
    timeout = kwargs.pop("timeout", getattr(config, "REQUEST_TIMEOUT", 45))
    last_error = None

    for attempt in range(1, retry_times + 1):
        try:
            return await client.request(method, url, timeout=timeout, **kwargs)
        except httpx.RequestError as exc:
            last_error = exc
            if attempt >= retry_times:
                break
            delay = min(2 ** (attempt - 1), 8)
            logger.warning(
                f"[httpx_util.request_with_retry] {exc.__class__.__name__} for {url}, "
                f"retry {attempt}/{retry_times} after {delay}s: {exc}"
            )
            await asyncio.sleep(delay)

    context = f"{method} {url} failed after {retry_times} attempts: {last_error}"
    record_request_failure(context)
    raise last_error  # type: ignore[misc]
