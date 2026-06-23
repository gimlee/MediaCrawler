# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/juejin/client.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# -*- coding: utf-8 -*-
"""Juejin API client.

Juejin's web APIs are protected by ByteDance anti-crawl signature params
(``aid``, ``uuid``, ``a_bogus``, ``msToken``, ``x-secsdk-csrf-token``) which
are injected by client-side JS. Reproducing the signature is fragile, so this
client issues every request *inside the browser page context* via
``page.evaluate(fetch)``. That way the browser's cookies and the same-origin
context are reused, and juejin treats the requests as first-party.

All endpoints verified against the live API (June 2026):
- search : GET  /search_api/v1/search            (query params, no signature)
- detail : POST /content_api/v1/article/detail   (needs extra body fields)
- comment: POST /interact_api/v1/comment/list    (uses item_id, not article_id)
- user   : POST /user_api/v1/user/get            (needs login for full data)
- query  : POST /content_api/v1/article/query_list (creator articles)
"""
import asyncio
import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page

from base.base_crawler import AbstractApiClient
from constant import juejin as juejin_constant
from model.m_juejin import JuejinComment, JuejinContent, JuejinCreator
from proxy.proxy_mixin import ProxyRefreshMixin
from tools import utils

if TYPE_CHECKING:
    from proxy.proxy_ip_pool import ProxyIpPool

from .exception import DataFetchError, ForbiddenError
from .field import CommentSort, CreatorArticleSort, SearchSort, SearchType
from .help import JuejinExtractor

# Static query params juejin's frontend appends to every API call. The device
# ``uuid`` is derived by juejin from cookies server-side, so we only need the
# fixed ``aid`` (web app id = 2608) and ``spider=0`` here.
_API_QS = "aid=2608&spider=0"


class JuejinClient(AbstractApiClient, ProxyRefreshMixin):

    def __init__(
        self,
        timeout: int = 15,
        proxy: Optional[str] = None,
        *,
        headers: Dict[str, str],
        playwright_page: Optional[Page] = None,
        cookie_dict: Dict[str, str],
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.default_headers = headers
        self.cookie_urls = [juejin_constant.JUEJIN_URL]
        self.cookie_dict = cookie_dict
        self.playwright_page = playwright_page
        self._extractor = JuejinExtractor()
        self.init_proxy_pool(proxy_ip_pool)

    # ------------------------------------------------------------------
    # Low-level browser-context fetch
    # ------------------------------------------------------------------
    async def _get(self, url: str) -> Dict:
        """GET a juejin API url from inside the browser page context."""
        if self.playwright_page is None:
            raise DataFetchError("JuejinClient requires a browser page to issue requests")
        await self._refresh_proxy_if_expired()
        # NOTE: do not use an AbortController here — in combination with
        # Playwright's page.evaluate it spuriously aborts otherwise-fast
        # requests. The timeout is enforced on the Python side instead.
        js = """
        async (url) => {
            const r = await fetch(url, {
                method: 'GET',
                headers: { 'content-type': 'application/json' },
                credentials: 'include',
            });
            const text = await r.text();
            let data = null;
            try { data = JSON.parse(text); } catch (e) { data = { _text: text }; }
            return { status: r.status, data: data };
        }
        """
        try:
            result = await asyncio.wait_for(
                self.playwright_page.evaluate(js, url), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise DataFetchError(f"GET {url} timed out after {self.timeout}s")
        except Exception as e:
            utils.logger.error(f"[JuejinClient._get] page.evaluate failed for {url}: {e}")
            raise DataFetchError(str(e))

        return self._handle_result(url, result)

    async def _post(self, url: str, payload: Optional[Dict] = None) -> Dict:
        """POST JSON to a juejin API url from inside the browser page context."""
        if self.playwright_page is None:
            raise DataFetchError("JuejinClient requires a browser page to issue requests")
        await self._refresh_proxy_if_expired()
        body = json.dumps(payload or {}, ensure_ascii=False)
        js = """
        async ([url, body]) => {
            const r = await fetch(url, {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                credentials: 'include',
                body: body,
            });
            const text = await r.text();
            let data = null;
            try { data = JSON.parse(text); } catch (e) { data = { _text: text }; }
            return { status: r.status, data: data };
        }
        """
        try:
            result = await asyncio.wait_for(
                self.playwright_page.evaluate(js, [url, body]), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise DataFetchError(f"POST {url} timed out after {self.timeout}s")
        except Exception as e:
            utils.logger.error(f"[JuejinClient._post] page.evaluate failed for {url}: {e}")
            raise DataFetchError(str(e))

        return self._handle_result(url, result)

    def _handle_result(self, url: str, result: Dict) -> Dict:
        status = result.get("status")
        data = result.get("data") or {}
        if status != 200:
            utils.logger.error(
                f"[JuejinClient] Request Url: {url}, status: {status}, body: {data}"
            )
            if status == 403:
                raise ForbiddenError(str(data))
            raise DataFetchError(str(data))

        # Juejin convention: err_no == 0 means success.
        err_no = data.get("err_no", 0) if isinstance(data, dict) else 0
        if err_no not in (0, None):
            err_msg = data.get("err_msg", "unknown juejin api error") if isinstance(data, dict) else ""
            utils.logger.error(
                f"[JuejinClient] Request Url: {url}, err_no: {err_no}, err_msg: {err_msg}"
            )
            raise DataFetchError(err_msg)
        return data

    async def request(self, method, url, **kwargs) -> Any:
        """Generic request implementation (required by AbstractApiClient)."""
        if str(method).upper() == "GET":
            return await self._get(url)
        return await self._post(url, kwargs.get("json"))

    async def pong(self) -> bool:
        """Juejin read APIs work without login when issued from the browser."""
        utils.logger.info("[JuejinClient.pong] Juejin public read APIs do not require login")
        return True

    async def update_cookies(
        self, browser_context: BrowserContext, urls: Optional[List[str]] = None
    ):
        """Update cookies from browser context."""
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            browser_context,
            urls=urls or self.cookie_urls,
        )
        self.default_headers["cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def search_raw(
        self,
        keyword: str,
        cursor: str = "0",
        limit: int = 20,
        search_type: SearchType = SearchType.GENERAL,
        sort_type: SearchSort = SearchSort.DEFAULT,
    ) -> Dict:
        """
        GET /search_api/v1/search. Returns raw response (with cursor/has_more).
        Note: juejin uses ``query`` (not ``keyword``) for this GET endpoint.
        """
        params = {
            "query": keyword,
            "id_type": 0,
            "cursor": str(cursor),
            "limit": int(limit),
            "search_type": int(search_type.value),
            "sort_type": int(sort_type.value),
            "version": 1,
        }
        url = (
            f"{juejin_constant.JUEJIN_API_URL}/search_api/v1/search"
            f"?{_API_QS}&{urlencode(params)}"
        )
        return await self._get(url)

    async def get_note_by_keyword(
        self,
        keyword: str,
        cursor: str = "0",
        limit: int = 20,
        search_type: SearchType = SearchType.GENERAL,
        sort_type: SearchSort = SearchSort.DEFAULT,
    ) -> List[JuejinContent]:
        """Search by keyword, returning parsed content models."""
        res = await self.search_raw(keyword, cursor, limit, search_type, sort_type)
        return self._extractor.extract_contents_from_search(res)

    @staticmethod
    def extract_cursor(json_data: Dict) -> str:
        """Extract next cursor from search/query_list response."""
        if not json_data:
            return ""
        cursor = json_data.get("cursor")
        if cursor is None:
            return ""
        return str(cursor)

    @staticmethod
    def has_more(json_data: Dict) -> bool:
        if not json_data:
            return False
        return bool(json_data.get("has_more", False))

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------
    async def get_article_info(self, article_id: str) -> Optional[JuejinContent]:
        """
        Get article detail.

        Juejin's public ``content_api/v1/article/detail`` returns the metadata
        (counts, author, category) but an *empty* body for the article text.
        To actually store the content body we therefore navigate the page to
        the article and read the rendered DOM (same approach zhihu uses for
        its HTML detail flow). The DOM body is merged back into the API result.
        """
        detail = await self._get_article_detail_api(article_id)

        body_text = await self._fetch_article_dom_body(article_id)
        if body_text:
            if detail is None:
                # The detail API failed (rare), but the DOM page still works.
                # Build a minimal content object from the DOM.
                detail = JuejinContent()
                detail.content_id = str(article_id)
                detail.content_type = juejin_constant.ARTICLE_NAME
                detail.content_url = (
                    f"{juejin_constant.JUEJIN_URL}/post/{article_id}"
                )
            if not (detail.content_text or "").strip():
                detail.content_text = body_text

        return detail

    async def _get_article_detail_api(
        self, article_id: str
    ) -> Optional[JuejinContent]:
        """
        POST /content_api/v1/article/detail. The extra body fields
        (req_from/client_type/...) are required by juejin or it returns err_no:2.
        """
        payload = {
            "article_id": str(article_id),
            "req_from": 1,
            "client_type": 2608,
            "forbid_count": False,
            "is_pre_load": False,
            "need_theme": True,
        }
        url = f"{juejin_constant.JUEJIN_API_URL}/content_api/v1/article/detail?{_API_QS}"
        try:
            res = await self._post(url, payload)
        except DataFetchError as e:
            utils.logger.warning(
                f"[JuejinClient._get_article_detail_api] detail API failed for "
                f"{article_id}: {e}, will rely on DOM body"
            )
            return None
        return self._extractor.extract_article_detail(res)

    async def _fetch_article_dom_body(self, article_id: str) -> str:
        """
        Navigate to the article page and read its rendered body text from the DOM.

        Juejin renders the article inside an element whose class contains
        ``article-view``. We grab its innerText, which is clean plain text.
        Returns "" if the body could not be read.
        """
        if self.playwright_page is None:
            return ""
        article_url = f"{juejin_constant.JUEJIN_URL}/post/{article_id}"
        try:
            await self.playwright_page.goto(
                article_url, wait_until="domcontentloaded"
            )
            # Give juejin's SPA a moment to render the body.
            await asyncio.sleep(2)
            text = await self.playwright_page.evaluate(
                """
                () => {
                    const el = document.querySelector('[class*="article-view"]')
                        || document.querySelector('.article-content')
                        || document.querySelector('article');
                    return el ? el.innerText.trim() : '';
                }
                """
            )
            return (text or "").strip()
        except Exception as e:
            utils.logger.warning(
                f"[JuejinClient._fetch_article_dom_body] failed for {article_id}: {e}"
            )
            return ""

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    async def get_root_comments(
        self,
        article_id: str,
        cursor: str = "0",
        limit: int = 20,
        sort_type: CommentSort = CommentSort.DEFAULT,
    ) -> Dict:
        """
        POST /interact_api/v1/comment/list.
        IMPORTANT: juejin comments are keyed by ``item_id`` (not ``article_id``)
        and require ``comment_type`` + ``item_type``.
        """
        payload = {
            "cursor": str(cursor),
            "item_id": str(article_id),
            "item_type": 2,
            "client_type": 2608,
            "limit": int(limit),
            "sort_type": int(sort_type.value),
            "comment_type": 2,
        }
        url = f"{juejin_constant.JUEJIN_API_URL}/interact_api/v1/comment/list?{_API_QS}"
        return await self._post(url, payload)

    async def get_note_all_comments(
        self,
        content: JuejinContent,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: Optional[int] = None,
    ) -> List[JuejinComment]:
        """Get all root-level comments for a given article."""
        result: List[JuejinComment] = []
        cursor = "0"
        has_more = True
        limit = 20

        while has_more:
            if max_count is not None and len(result) >= max_count:
                break
            try:
                res = await self.get_root_comments(content.content_id, cursor, limit)
            except ForbiddenError as e:
                utils.logger.warning(
                    f"[JuejinClient.get_note_all_comments] Forbidden for content {content.content_id}: {e}"
                )
                break

            if not res:
                break

            has_more = self.has_more(res)
            next_cursor = self.extract_cursor(res)
            comments = self._extractor.extract_comments(res.get("data") or [])

            if not comments:
                break

            if max_count is not None:
                remaining = max_count - len(result)
                comments = comments[:remaining]

            # backfill content_id on each comment
            for c in comments:
                c.content_id = content.content_id

            if callback:
                await callback(comments)

            result.extend(comments)

            if next_cursor and next_cursor != cursor:
                cursor = next_cursor
            else:
                break

            if not has_more:
                break

            sleep_seconds = await utils.crawler_sleep(crawl_interval)
            utils.logger.info(
                f"[JuejinClient.get_note_all_comments] Sleeping for {sleep_seconds:.2f}s "
                f"before next comment page for content {content.content_id}"
            )
        return result

    # ------------------------------------------------------------------
    # Creator / user info
    # ------------------------------------------------------------------
    async def get_creator_info(self, user_id: str) -> Optional[JuejinCreator]:
        """
        POST /user_api/v1/user/get. Full data needs login; without login it
        returns the public profile fields.
        """
        payload = {"user_id": str(user_id), "not_self": "1"}
        url = f"{juejin_constant.JUEJIN_API_URL}/user_api/v1/user/get?{_API_QS}"
        res = await self._post(url, payload)
        return self._extractor.extract_creator(res)

    async def get_creator_articles(
        self,
        user_id: str,
        cursor: str = "0",
        sort_type: CreatorArticleSort = CreatorArticleSort.TIME,
    ) -> Dict:
        """POST /content_api/v1/article/query_list (creator article list)."""
        payload = {
            "user_id": str(user_id),
            "sort_type": int(sort_type.value),
            "cursor": str(cursor),
        }
        url = f"{juejin_constant.JUEJIN_API_URL}/content_api/v1/article/query_list?{_API_QS}"
        return await self._post(url, payload)

    async def get_all_articles_by_creator(
        self,
        creator: JuejinCreator,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: Optional[int] = None,
    ) -> List[JuejinContent]:
        """Paginate through all articles of a creator."""
        all_contents: List[JuejinContent] = []
        cursor = "0"
        has_more = True

        while has_more:
            if max_count is not None and len(all_contents) >= max_count:
                break
            try:
                res = await self.get_creator_articles(creator.user_id, cursor)
            except ForbiddenError as e:
                utils.logger.warning(
                    f"[JuejinClient.get_all_articles_by_creator] Forbidden for creator {creator.user_id}: {e}"
                )
                break

            if not res:
                break

            has_more = self.has_more(res)
            next_cursor = self.extract_cursor(res)
            contents = self._extractor.extract_contents_from_query_list(res)

            if not contents:
                break

            if max_count is not None:
                remaining = max_count - len(all_contents)
                contents = contents[:remaining]

            if callback:
                await callback(contents)

            all_contents.extend(contents)

            if next_cursor and next_cursor != cursor:
                cursor = next_cursor
            else:
                break

            if not has_more:
                break

            sleep_seconds = await utils.crawler_sleep(crawl_interval)
            utils.logger.info(
                f"[JuejinClient.get_all_articles_by_creator] Sleeping for {sleep_seconds:.2f}s "
                f"before next article page for creator {creator.user_id}"
            )
        return all_contents
