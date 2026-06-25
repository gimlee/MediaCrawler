# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/juejin/core.py
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
import asyncio
import os
from typing import Dict, List, Optional

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from model.m_juejin import JuejinContent, JuejinCreator
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import juejin as juejin_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from tools.resume_manager import resume_manager
from var import crawler_type_var, source_keyword_var

from .client import JuejinClient
from .exception import DataFetchError
from .field import SearchSort, SearchType
from .help import JuejinExtractor
from .login import JuejinLogin


class JuejinCrawler(AbstractCrawler):
    context_page: Page
    juejin_client: JuejinClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://juejin.cn"
        self.cookie_urls = [self.index_url]
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        self._extractor = JuejinExtractor()
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool for automatic proxy refresh

    async def start(self) -> None:
        """
        Start the crawler.
        """
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[JuejinCrawler] Launching browser in CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[JuejinCrawler] Launching browser in standard mode")
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.HEADLESS,
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, wait_until="domcontentloaded")

            # Juejin read APIs are issued from inside the browser page context
            # (page.evaluate fetch). Navigating to the search page first warms up
            # the same-origin context and lets juejin's SDK set anti-crawl cookies.
            utils.logger.info(
                "[JuejinCrawler.start] Warming up juejin context on search page ..."
            )
            try:
                await self.context_page.goto(
                    f"{self.index_url}/search?query=python&type=0",
                    wait_until="domcontentloaded",
                )
                await asyncio.sleep(3)
            except Exception as e:
                utils.logger.warning(f"[JuejinCrawler.start] search page warm-up failed: {e}")

            self.juejin_client = await self.create_juejin_client(httpx_proxy_format)
            # Juejin public read APIs do not require login. Only trigger login
            # flow when cookies are explicitly provided for non-public access.
            if config.LOGIN_TYPE == "cookie" and config.COOKIES:
                login_obj = JuejinLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.juejin_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                utils.logger.warning(
                    f"[JuejinCrawler.start] Unsupported crawler type: {config.CRAWLER_TYPE}"
                )

            utils.logger.info("[JuejinCrawler.start] Juejin Crawler finished ...")

    async def search(self) -> None:
        """Search for articles and retrieve their comment information."""
        utils.logger.info("[JuejinCrawler.search] Begin search juejin keywords")
        page_size = 20  # juejin search page size fixed value
        start_page = config.START_PAGE

        for keyword in config.KEYWORDS.split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            source_keyword_var.set(keyword)
            utils.logger.info(
                f"[JuejinCrawler.search] Current search keyword: {keyword}"
            )

            cursor = "0"
            has_more = True
            fetched_count = 0
            page = 1

            while has_more and fetched_count < config.CRAWLER_MAX_NOTES_COUNT:
                try:
                    is_before_start = page < start_page
                    is_resume_done = (
                        not is_before_start
                        and resume_manager.is_page_done(keyword, page)
                    )
                    if is_before_start or is_resume_done:
                        if is_before_start:
                            utils.logger.info(
                                f"[JuejinCrawler.search] Skip page {page} (cursor={cursor})"
                            )
                        else:
                            utils.logger.info(
                                f"[JuejinCrawler.search] Resume skip done page, "
                                f"keyword: {keyword}, page: {page}, cursor: {cursor}"
                            )

                        raw_res = await self.juejin_client.search_raw(
                            keyword=keyword,
                            cursor=cursor,
                            limit=page_size,
                            search_type=SearchType.GENERAL,
                            sort_type=SearchSort.DEFAULT,
                        )
                        has_more = JuejinClient.has_more(raw_res)
                        next_cursor = JuejinClient.extract_cursor(raw_res)
                        if next_cursor and next_cursor != cursor:
                            cursor = next_cursor
                        else:
                            has_more = False
                        page += 1
                        if has_more:
                            await utils.crawler_sleep(
                                config.CRAWLER_PAGE_SLEEP_SEC
                            )
                        continue

                    page_cursor = cursor
                    resume_manager.mark_page_running(
                        keyword, page, cursor=page_cursor
                    )
                    utils.logger.info(
                        f"[JuejinCrawler.search] search juejin keyword: {keyword}, page: {page}, cursor: {cursor}"
                    )

                    # Single search call; extract paging info and contents from same response.
                    raw_res = await self.juejin_client.search_raw(
                        keyword=keyword,
                        cursor=cursor,
                        limit=page_size,
                        search_type=SearchType.GENERAL,
                        sort_type=SearchSort.DEFAULT,
                    )
                    content_list: List[JuejinContent] = (
                        self._extractor.extract_contents_from_search(raw_res)
                    )
                    if not content_list:
                        utils.logger.info("No more content!")
                        break

                    sleep_seconds = await utils.crawler_sleep(config.CRAWLER_PAGE_SLEEP_SEC)
                    utils.logger.info(
                        f"[JuejinCrawler.search] Sleeping for {sleep_seconds:.2f} seconds after page {page}"
                    )

                    current_page = page
                    page += 1
                    fetched_count += len(content_list)

                    content_list_for_comments: List[JuejinContent] = []
                    page_has_failed_detail = False
                    for content in content_list:
                        resume_manager.upsert_item(
                            content.content_id, keyword=keyword, content_type=content.content_type
                        )
                        if resume_manager.should_skip_detail(content.content_id):
                            utils.logger.info(
                                f"[JuejinCrawler.search] Resume skip done content detail: {content.content_id}"
                            )
                            content_list_for_comments.append(content)
                            continue
                        try:
                            resume_manager.mark_detail_running(
                                content.content_id,
                                keyword=keyword,
                                content_type=content.content_type,
                            )
                            detail_content = await self.fetch_content_detail(content)
                            if not detail_content:
                                page_has_failed_detail = True
                                resume_manager.mark_detail_failed(
                                    content.content_id,
                                    keyword=keyword,
                                    content_type=content.content_type,
                                )
                                continue
                            await juejin_store.update_juejin_content(detail_content)
                            resume_manager.mark_detail_done(
                                detail_content.content_id,
                                keyword=keyword,
                                content_type=detail_content.content_type,
                            )
                            content_list_for_comments.append(detail_content)
                        except Exception:
                            page_has_failed_detail = True
                            resume_manager.mark_detail_failed(
                                content.content_id,
                                keyword=keyword,
                                content_type=content.content_type,
                            )
                            utils.logger.warning(
                                f"[JuejinCrawler.search] Detail fetch failed, skip this content, "
                                f"content_id: {content.content_id}",
                                exc_info=True,
                            )
                            continue

                    await self.batch_get_content_comments(content_list_for_comments)

                    # advance cursor from the search response
                    has_more = JuejinClient.has_more(raw_res)
                    next_cursor = JuejinClient.extract_cursor(raw_res)
                    if next_cursor and next_cursor != cursor:
                        cursor = next_cursor
                    else:
                        has_more = False

                    if page_has_failed_detail:
                        resume_manager.mark_page_failed(
                            keyword, current_page, cursor=page_cursor
                        )
                    else:
                        resume_manager.mark_page_done(
                            keyword, current_page, cursor=page_cursor
                        )
                except DataFetchError as e:
                    resume_manager.mark_page_failed(
                        keyword, page, cursor=cursor
                    )
                    utils.logger.error(
                        f"[JuejinCrawler.search] Search content error for keyword "
                        f"{keyword}, page {page}: {e}. Stop this keyword and continue."
                    )
                    break

    async def fetch_content_detail(self, content: JuejinContent) -> Optional[JuejinContent]:
        """
        Fetch full article detail before storing. The search list only returns
        metadata (title/brief/counts), so the body text comes from the detail API.
        """
        if not content or not content.content_id:
            return None

        detail_content = await self.juejin_client.get_article_info(content.content_id)
        if not detail_content:
            utils.logger.warning(
                f"[JuejinCrawler.fetch_content_detail] Detail not found, content_id: {content.content_id}"
            )
            return None

        self.merge_content_summary(detail_content, content)
        if not (detail_content.content_text or "").strip():
            # Juejin's public API/DOM sometimes returns no body (gated content,
            # deleted articles, ...). We still keep the row: it carries useful
            # metadata (title/brief/counts/author) from the search list.
            utils.logger.info(
                f"[JuejinCrawler.fetch_content_detail] Empty content_text, keeping metadata only, "
                f"content_id: {content.content_id}"
            )

        sleep_seconds = await utils.crawler_sleep(config.CRAWLER_DETAIL_SLEEP_SEC)
        utils.logger.info(
            f"[JuejinCrawler.fetch_content_detail] Sleeping for {sleep_seconds:.2f} seconds "
            f"after detail fetch for content {content.content_id}"
        )
        return detail_content

    @staticmethod
    def merge_content_summary(detail_content: JuejinContent, summary_content: JuejinContent) -> None:
        """Keep useful search-list metadata when the detail page omits it."""
        summary_data = summary_content.model_dump()
        for field_name, summary_value in summary_data.items():
            if summary_value in ("", None, 0):
                continue
            detail_value = getattr(detail_content, field_name, None)
            if detail_value in ("", None, 0):
                setattr(detail_content, field_name, summary_value)

    async def batch_get_content_comments(self, content_list: List[JuejinContent]) -> None:
        """Batch get content comments."""
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                "[JuejinCrawler.batch_get_content_comments] Crawling comment mode is not enabled"
            )
            return

        semaphore = asyncio.Semaphore(config.get_platform_max_concurrency_num("juejin"))
        task_list = []
        for content_item in content_list:
            if resume_manager.should_skip_comment(content_item.content_id):
                utils.logger.info(
                    f"[JuejinCrawler.batch_get_content_comments] Resume skip done comments, "
                    f"content_id: {content_item.content_id}"
                )
                continue
            task = asyncio.create_task(
                self.get_comments(content_item, semaphore), name=content_item.content_id
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, content_item: JuejinContent, semaphore: asyncio.Semaphore) -> None:
        """Get content comments."""
        async with semaphore:
            utils.logger.info(
                f"[JuejinCrawler.get_comments] Begin get content comments {content_item.content_id}"
            )
            resume_manager.mark_comment_running(
                content_item.content_id,
                keyword=source_keyword_var.get(),
                content_type=content_item.content_type,
            )

            sleep_seconds = await utils.crawler_sleep(config.CRAWLER_COMMENT_SLEEP_SEC)
            utils.logger.info(
                f"[JuejinCrawler.get_comments] Sleeping for {sleep_seconds:.2f} seconds "
                f"before fetching comments for content {content_item.content_id}"
            )

            try:
                await self.juejin_client.get_note_all_comments(
                    content=content_item,
                    crawl_interval=config.CRAWLER_COMMENT_SLEEP_SEC,
                    callback=juejin_store.batch_update_juejin_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
                resume_manager.mark_comment_done(
                    content_item.content_id,
                    keyword=source_keyword_var.get(),
                    content_type=content_item.content_type,
                )
            except Exception:
                resume_manager.mark_comment_failed(
                    content_item.content_id,
                    keyword=source_keyword_var.get(),
                    content_type=content_item.content_type,
                )
                raise

    async def get_creators_and_notes(self) -> None:
        """Get creator's information and their articles and comments."""
        utils.logger.info(
            "[JuejinCrawler.get_creators_and_notes] Begin get juejin creators"
        )
        for user_id in config.JUEJIN_CREATOR_ID_LIST:
            utils.logger.info(
                f"[JuejinCrawler.get_creators_and_notes] Begin get creator {user_id}"
            )
            creator_info: Optional[JuejinCreator] = await self.juejin_client.get_creator_info(user_id)
            if not creator_info:
                utils.logger.info(
                    f"[JuejinCrawler.get_creators_and_notes] Creator {user_id} not found"
                )
                continue

            utils.logger.info(
                f"[JuejinCrawler.get_creators_and_notes] Creator info: {creator_info}"
            )
            await juejin_store.save_creator(creator=creator_info)

            all_content_list = await self.juejin_client.get_all_articles_by_creator(
                creator=creator_info,
                crawl_interval=config.CRAWLER_PAGE_SLEEP_SEC,
                max_count=config.CRAWLER_MAX_NOTES_COUNT,
            )

            # Fetch full detail for each article so the body text is stored.
            detail_list: List[JuejinContent] = []
            for content in all_content_list:
                resume_manager.upsert_item(
                    content.content_id, content_type=content.content_type
                )
                if resume_manager.should_skip_detail(content.content_id):
                    detail_list.append(content)
                    continue
                try:
                    resume_manager.mark_detail_running(
                        content.content_id, content_type=content.content_type
                    )
                    detail_content = await self.fetch_content_detail(content)
                    if detail_content:
                        await juejin_store.update_juejin_content(detail_content)
                        resume_manager.mark_detail_done(
                            detail_content.content_id,
                            content_type=detail_content.content_type,
                        )
                        detail_list.append(detail_content)
                    else:
                        resume_manager.mark_detail_failed(
                            content.content_id, content_type=content.content_type
                        )
                except Exception:
                    resume_manager.mark_detail_failed(
                        content.content_id, content_type=content.content_type
                    )
                    utils.logger.warning(
                        f"[JuejinCrawler.get_creators_and_notes] Detail fetch failed, "
                        f"content_id: {content.content_id}",
                        exc_info=True,
                    )

            await self.batch_get_content_comments(detail_list)

    async def get_note_detail(
        self, article_id: str, semaphore: asyncio.Semaphore
    ) -> Optional[JuejinContent]:
        """Get note detail by article id."""
        async with semaphore:
            utils.logger.info(
                f"[JuejinCrawler.get_specified_notes] Begin get specified note {article_id}"
            )
            result = await self.juejin_client.get_article_info(article_id)

            sleep_seconds = await utils.crawler_sleep(config.CRAWLER_DETAIL_SLEEP_SEC)
            utils.logger.info(
                f"[JuejinCrawler.get_note_detail] Sleeping for {sleep_seconds:.2f} seconds "
                f"after fetching article details {article_id}"
            )
            return result

    async def get_specified_notes(self) -> None:
        """Get the information and comments of the specified articles."""
        task_list = []
        task_ids = []
        semaphore = asyncio.Semaphore(
            config.get_platform_max_concurrency_num("juejin")
        )
        for article_id in config.JUEJIN_SPECIFIED_ID_LIST:
            article_id = str(article_id).strip()
            if not article_id:
                continue
            # accept full url or id
            if article_id.startswith("http"):
                tail = article_id.rstrip("/").split("/")[-1]
                article_id = tail
            resume_manager.upsert_item(article_id, content_type="article")
            if (
                resume_manager.should_skip_detail(article_id)
                and resume_manager.should_skip_comment(article_id)
            ):
                utils.logger.info(
                    f"[JuejinCrawler.get_specified_notes] Resume skip done content: {article_id}"
                )
                continue
            task_ids.append(article_id)
            task_list.append(
                self.get_note_detail(
                    article_id=article_id,
                    semaphore=semaphore,
                )
            )

        need_get_comment_notes: List[JuejinContent] = []
        note_details = await asyncio.gather(*task_list)
        for index, note_detail in enumerate(note_details):
            if not note_detail:
                utils.logger.info(
                    f"[JuejinCrawler.get_specified_notes] Note {task_ids[index]} not found"
                )
                resume_manager.mark_detail_failed(task_ids[index])
                continue

            need_get_comment_notes.append(note_detail)
            await juejin_store.update_juejin_content(note_detail)
            resume_manager.mark_detail_done(note_detail.content_id, content_type=note_detail.content_type)

        await self.batch_get_content_comments(need_get_comment_notes)

    async def create_juejin_client(self, httpx_proxy: Optional[str]) -> JuejinClient:
        """Create juejin client."""
        utils.logger.info(
            "[JuejinCrawler.create_juejin_client] Begin create juejin API client ..."
        )
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            self.browser_context,
            urls=self.cookie_urls,
        )
        juejin_client_obj = JuejinClient(
            timeout=config.REQUEST_TIMEOUT,
            proxy=httpx_proxy,
            headers={
                "accept": "application/json",
                "accept-language": "zh-CN,zh;q=0.9",
                "cookie": cookie_str,
                "origin": "https://juejin.cn",
                "referer": "https://juejin.cn/",
                "user-agent": self.user_agent,
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
        )
        return juejin_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context."""
        utils.logger.info(
            "[JuejinCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                channel="chrome",
            )
            return browser_context
        else:
            browser = await chromium.launch(
                headless=headless, proxy=playwright_proxy, channel="chrome"
            )  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser using CDP mode."""
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[JuejinCrawler] CDP browser info: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(
                f"[JuejinCrawler] CDP mode launch failed, falling back to standard mode: {e}"
            )
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def close(self):
        """Close browser context."""
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[JuejinCrawler.close] Browser context closed ...")
