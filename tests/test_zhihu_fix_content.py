# -*- coding: utf-8 -*-

import pytest

from constant import zhihu as zhihu_constant
from media_platform.zhihu import ZhihuCrawler
from model.m_zhihu import ZhihuContent
from store import zhihu as zhihu_store


@pytest.mark.asyncio
async def test_zhihu_fix_empty_content_text_updates_non_empty_details(monkeypatch):
    crawler = ZhihuCrawler()
    updated_contents = []
    requested_urls = []

    empty_contents = [
        ZhihuContent(
            content_id="answer_1",
            content_type=zhihu_constant.ANSWER_NAME,
            content_url="https://www.zhihu.com/question/100/answer/answer_1",
            question_id="100",
            title="Original title",
        ),
        ZhihuContent(
            content_id="article_1",
            content_type=zhihu_constant.ARTICLE_NAME,
            content_url="https://zhuanlan.zhihu.com/p/article_1",
            title="Still empty",
        ),
    ]

    async def fake_get_empty_content_text_contents():
        return empty_contents

    async def fake_get_note_detail(full_note_url, semaphore):
        requested_urls.append(full_note_url)
        if full_note_url.endswith("answer_1"):
            return ZhihuContent(
                content_id="answer_1",
                content_type=zhihu_constant.ANSWER_NAME,
                content_url=full_note_url,
                question_id="100",
                content_text="fixed answer text",
            )
        return ZhihuContent(
            content_id="article_1",
            content_type=zhihu_constant.ARTICLE_NAME,
            content_url=full_note_url,
            content_text="",
        )

    async def fake_update_zhihu_content(content):
        updated_contents.append(content)

    monkeypatch.setattr(
        zhihu_store,
        "get_empty_content_text_contents",
        fake_get_empty_content_text_contents,
    )
    monkeypatch.setattr(crawler, "get_note_detail", fake_get_note_detail)
    monkeypatch.setattr(zhihu_store, "update_zhihu_content", fake_update_zhihu_content)

    await crawler.fix_empty_content_text()

    assert requested_urls == [
        "https://www.zhihu.com/question/100/answer/answer_1",
        "https://zhuanlan.zhihu.com/p/article_1",
    ]
    assert len(updated_contents) == 1
    assert updated_contents[0].content_id == "answer_1"
    assert updated_contents[0].content_text == "fixed answer text"
    assert updated_contents[0].title == "Original title"
