import asyncio
from types import SimpleNamespace

import config
import pytest

from media_platform.juejin.core import JuejinCrawler
from model.m_juejin import JuejinContent, JuejinCreator


async def _no_sleep(_):
    return 0.0


def _disable_resume_item_writes(monkeypatch):
    from media_platform.juejin import core

    for method_name in (
        "upsert_item",
        "mark_detail_running",
        "mark_detail_done",
        "mark_detail_failed",
        "mark_comment_running",
        "mark_comment_done",
        "mark_comment_failed",
    ):
        monkeypatch.setattr(core.resume_manager, method_name, lambda *args, **kwargs: None)
    monkeypatch.setattr(
        core.resume_manager, "should_skip_detail", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(
        core.resume_manager, "should_skip_comment", lambda *args, **kwargs: False
    )


@pytest.mark.asyncio
async def test_juejin_uses_shared_comment_limit(monkeypatch):
    crawler = JuejinCrawler()
    seen = {}

    async def fake_all_comments(**kwargs):
        seen.update(kwargs)
        return []

    crawler.juejin_client = SimpleNamespace(
        get_note_all_comments=fake_all_comments
    )
    monkeypatch.setattr(config, "CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES", 7)
    monkeypatch.setattr(
        "media_platform.juejin.core.utils.crawler_sleep", _no_sleep
    )
    _disable_resume_item_writes(monkeypatch)

    await crawler.get_comments(
        JuejinContent(content_id="a1"), asyncio.Semaphore(1)
    )

    assert seen["max_count"] == 7


@pytest.mark.asyncio
async def test_creator_mode_honors_shared_max_notes(monkeypatch):
    crawler = JuejinCrawler()
    creator = JuejinCreator(user_id="u1")
    seen = {}

    class Client:
        async def get_creator_info(self, user_id):
            return creator

        async def get_all_articles_by_creator(self, **kwargs):
            seen.update(kwargs)
            return []

    crawler.juejin_client = Client()
    monkeypatch.setattr(config, "JUEJIN_CREATOR_ID_LIST", ["u1"])
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 12)
    monkeypatch.setattr(config, "CRAWLER_PAGE_SLEEP_SEC", 0.25)
    monkeypatch.setattr(
        "media_platform.juejin.core.juejin_store.save_creator",
        _save_creator_noop,
    )

    await crawler.get_creators_and_notes()

    assert seen["max_count"] == 12
    assert seen["crawl_interval"] == 0.25
    assert seen.get("callback") is None


async def _save_creator_noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_standard_mode_forwards_playwright_proxy(monkeypatch):
    from media_platform.juejin import core

    crawler = JuejinCrawler()
    proxy = {"server": "http://127.0.0.1:8080"}
    captured = {}

    class ProxyPool:
        async def get_proxy(self):
            return object()

    class FakePage:
        async def goto(self, *args, **kwargs):
            return None

    class FakeContext:
        async def add_init_script(self, *args, **kwargs):
            return None

        async def new_page(self):
            return FakePage()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return SimpleNamespace(chromium=object())

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_create_ip_pool(*args, **kwargs):
        return ProxyPool()

    async def fake_launch_browser(chromium, playwright_proxy, *args, **kwargs):
        captured["proxy"] = playwright_proxy
        return FakeContext()

    async def fake_create_client(httpx_proxy):
        return SimpleNamespace()

    async def fake_search():
        return None

    monkeypatch.setattr(config, "ENABLE_IP_PROXY", True)
    monkeypatch.setattr(config, "ENABLE_CDP_MODE", False)
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "LOGIN_TYPE", "qrcode")
    monkeypatch.setattr(core, "create_ip_pool", fake_create_ip_pool)
    monkeypatch.setattr(
        core.utils, "format_proxy_info", lambda _: (proxy, "http://127.0.0.1:8080")
    )
    monkeypatch.setattr(core, "async_playwright", FakePlaywrightManager)
    monkeypatch.setattr(core.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(crawler, "launch_browser", fake_launch_browser)
    monkeypatch.setattr(crawler, "create_juejin_client", fake_create_client)
    monkeypatch.setattr(crawler, "search", fake_search)

    await crawler.start()

    assert captured["proxy"] == proxy


@pytest.mark.asyncio
async def test_specified_notes_share_one_detail_semaphore(monkeypatch):
    crawler = JuejinCrawler()
    semaphore_ids = []

    async def fake_get_note_detail(article_id, semaphore):
        semaphore_ids.append(id(semaphore))
        return None

    monkeypatch.setattr(config, "JUEJIN_SPECIFIED_ID_LIST", ["a1", "a2", "a3"])
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
    monkeypatch.setattr(crawler, "get_note_detail", fake_get_note_detail)
    _disable_resume_item_writes(monkeypatch)

    await crawler.get_specified_notes()

    assert len(semaphore_ids) == 3
    assert len(set(semaphore_ids)) == 1


@pytest.mark.asyncio
async def test_resume_done_page_advances_cursor_before_next_page(monkeypatch):
    crawler = JuejinCrawler()
    requested_cursors = []

    async def fake_search_raw(**kwargs):
        requested_cursors.append(kwargs["cursor"])
        if kwargs["cursor"] == "0":
            return {"data": [], "cursor": "20", "has_more": True}
        return {"data": [], "cursor": "40", "has_more": False}

    crawler.juejin_client = SimpleNamespace(search_raw=fake_search_raw)
    monkeypatch.setattr(config, "KEYWORDS", "python")
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.is_page_done",
        lambda keyword, page: page == 1,
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.mark_page_running",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.utils.crawler_sleep", _no_sleep
    )

    await crawler.search()

    assert requested_cursors == ["0", "20"]


@pytest.mark.asyncio
async def test_start_page_traversal_does_not_consume_note_limit(monkeypatch):
    crawler = JuejinCrawler()
    requested_cursors = []

    async def fake_search_raw(**kwargs):
        requested_cursors.append(kwargs["cursor"])
        if kwargs["cursor"] == "0":
            return {"data": [], "cursor": "20", "has_more": True}
        return {"data": [], "cursor": "40", "has_more": False}

    crawler.juejin_client = SimpleNamespace(search_raw=fake_search_raw)
    monkeypatch.setattr(config, "KEYWORDS", "python")
    monkeypatch.setattr(config, "START_PAGE", 2)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.is_page_done",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.mark_page_running",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.utils.crawler_sleep", _no_sleep
    )

    await crawler.search()

    assert requested_cursors == ["0", "20"]


@pytest.mark.asyncio
async def test_search_persists_page_starting_cursor(monkeypatch):
    crawler = JuejinCrawler()
    running_calls = []
    done_calls = []
    content = JuejinContent(content_id="a1", title="summary")

    async def fake_search_raw(**kwargs):
        return {
            "data": [{"article_id": "a1", "article_info": {"title": "summary"}}],
            "cursor": "20",
            "has_more": False,
        }

    async def fake_fetch_content_detail(summary):
        return summary

    async def fake_store_content(*args, **kwargs):
        return None

    async def fake_comments(*args, **kwargs):
        return None

    crawler.juejin_client = SimpleNamespace(search_raw=fake_search_raw)
    monkeypatch.setattr(
        crawler._extractor, "extract_contents_from_search", lambda _: [content]
    )
    monkeypatch.setattr(crawler, "fetch_content_detail", fake_fetch_content_detail)
    monkeypatch.setattr(crawler, "batch_get_content_comments", fake_comments)
    monkeypatch.setattr(
        "media_platform.juejin.core.juejin_store.update_juejin_content",
        fake_store_content,
    )
    monkeypatch.setattr(config, "KEYWORDS", "python")
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.is_page_done",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.mark_page_running",
        lambda *args, **kwargs: running_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.resume_manager.mark_page_done",
        lambda *args, **kwargs: done_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "media_platform.juejin.core.utils.crawler_sleep", _no_sleep
    )
    _disable_resume_item_writes(monkeypatch)

    await crawler.search()

    assert running_calls == [(("python", 1), {"cursor": "0"})]
    assert done_calls == [(("python", 1), {"cursor": "0"})]
