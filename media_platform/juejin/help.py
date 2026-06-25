# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/juejin/help.py
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
from typing import Dict, List, Optional

from constant import juejin as juejin_constant
from model.m_juejin import JuejinComment, JuejinContent, JuejinCreator
from tools.crawler_util import extract_text_from_html


def _to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class JuejinExtractor:
    """Extract Juejin API response into pydantic models."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def extract_contents_from_search(self, json_data: Dict) -> List[JuejinContent]:
        """
        Extract article contents from search_api/v1/search response.
        Real shape (verified):
            { err_no, err_msg, data: [ { result_type, result_model: { article_id, article_info, author_user_info, category, ... }, ... } ],
              count, cursor, has_more }
        result_type == 2 means an article.
        """
        if not json_data:
            return []

        data: List[Dict] = json_data.get("data", []) or []
        result: List[JuejinContent] = []
        for item in data:
            # The real article payload is nested under ``result_model``.
            model = item.get("result_model") if isinstance(item, dict) else None
            content = self._extract_content_from_search_item(model if model else item)
            if content:
                result.append(content)
        return result

    def _extract_content_from_search_item(self, item: Dict) -> Optional[JuejinContent]:
        if not item:
            return None

        article_info = item.get("article_info") or {}
        article_id = item.get("article_id") or article_info.get("article_id")
        if not article_id:
            return None

        res = JuejinContent()
        res.content_id = str(article_id)
        res.content_type = juejin_constant.ARTICLE_NAME
        res.content_url = f"{juejin_constant.JUEJIN_URL}/post/{res.content_id}"
        res.title = article_info.get("title", "") or ""
        # juejin uses ``brief_content`` in list responses
        res.desc = (
            article_info.get("brief_content")
            or article_info.get("brief")
            or ""
        )
        res.created_time = _to_int(article_info.get("ctime"))
        res.updated_time = _to_int(article_info.get("mtime"))
        res.view_count = _to_int(article_info.get("view_count"))
        res.digg_count = _to_int(article_info.get("digg_count"))
        res.comment_count = _to_int(article_info.get("comment_count"))
        res.collect_count = _to_int(article_info.get("collect_count"))
        res.share_count = _to_int(article_info.get("share_count"))

        # category
        category = item.get("category") or {}
        res.category_name = category.get("category_name", "") or ""

        # author
        author = item.get("author_user_info") or {}
        self._fill_author(res, author)
        return res

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------
    def extract_article_detail(self, json_data: Dict) -> Optional[JuejinContent]:
        """
        Extract content_api/v1/article/detail response.
        Real shape (verified):
            { err_no, err_msg, data: { article_id, article_info: {...}, author_user_info, category, tags, ... } }
        Note: for some (older/edited) articles juejin returns empty content/title
        in the API even though counts are populated. Such rows are returned with
        empty content_text so the caller can decide to skip.
        """
        if not json_data:
            return None

        data = json_data.get("data") or {}
        if not data:
            return None

        article_info = data.get("article_info") or {}
        article_id = data.get("article_id") or article_info.get("article_id")
        if not article_id:
            return None

        res = JuejinContent()
        res.content_id = str(article_id)
        res.content_type = juejin_constant.ARTICLE_NAME
        res.content_url = f"{juejin_constant.JUEJIN_URL}/post/{res.content_id}"
        res.title = article_info.get("title", "") or ""
        res.desc = (
            article_info.get("brief_content")
            or article_info.get("brief")
            or ""
        )

        # content field holds the html/markdown body; mark_content is the markdown source
        content_body = (
            article_info.get("content")
            or article_info.get("mark_content")
            or ""
        )
        res.content_text = self._clean_content(content_body)

        res.created_time = _to_int(article_info.get("ctime"))
        res.updated_time = _to_int(article_info.get("mtime"))
        res.view_count = _to_int(article_info.get("view_count"))
        res.digg_count = _to_int(article_info.get("digg_count"))
        res.comment_count = _to_int(article_info.get("comment_count"))
        res.collect_count = _to_int(article_info.get("collect_count"))
        res.share_count = _to_int(article_info.get("share_count"))

        category = data.get("category") or {}
        res.category_name = category.get("category_name", "") or ""

        author = data.get("author_user_info") or data.get("user_info") or {}
        self._fill_author(res, author)
        return res

    # ------------------------------------------------------------------
    # Creator article list
    # ------------------------------------------------------------------
    def extract_contents_from_query_list(self, json_data: Dict) -> List[JuejinContent]:
        """
        Extract content_api/v1/article/query_list response.
        Real shape:
            { err_no, err_msg, data: [ { article_id, article_info, author_user_info, category, ... }, ... ], cursor, has_more }
        """
        if not json_data:
            return []

        data: List[Dict] = json_data.get("data", []) or []
        result: List[JuejinContent] = []
        for item in data:
            content = self._extract_content_from_search_item(item)
            if content:
                result.append(content)
        return result

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    def extract_comments(self, comments: List[Dict]) -> List[JuejinComment]:
        """
        Extract interact_api/v1/comment/list response data items.
        Each item: { comment_id, comment_info: { comment_content, ctime, digg_count, reply_count, ... }, user_info: {...} }
        """
        if not comments:
            return []
        result: List[JuejinComment] = []
        for comment in comments:
            item = self._extract_comment(comment)
            if item:
                result.append(item)
        return result

    def _extract_comment(self, comment: Dict) -> Optional[JuejinComment]:
        if not comment:
            return None

        comment_info = comment.get("comment_info") or {}
        reply_info = comment.get("reply_info") or {}
        info = comment_info or reply_info
        is_reply = bool(reply_info)
        comment_id = (
            info.get("comment_id")
            or info.get("reply_id")
            or comment.get("comment_id")
            or comment.get("reply_id")
        )
        if not comment_id:
            return None

        res = JuejinComment()
        res.comment_id = str(comment_id)
        content = (
            info.get("reply_content")
            if is_reply
            else info.get("comment_content")
        )
        res.content = extract_text_from_html(content or "")
        res.publish_time = _to_int(info.get("ctime"))
        res.sub_comment_count = 0 if is_reply else _to_int(info.get("reply_count"))
        res.like_count = _to_int(info.get("digg_count"))
        parent_id = (
            info.get("reply_comment_id")
            or info.get("reply_to_comment_id")
            or info.get("parent_comment_id")
            or (info.get("reply_id") if not is_reply else "")
            or ""
        )
        res.parent_comment_id = str(parent_id)

        user_info = comment.get("user_info") or {}
        res.user_id = str(user_info.get("user_id", "") or "")
        res.user_nickname = user_info.get("user_name", "") or ""
        res.user_avatar = user_info.get("avatar_large", "") or user_info.get("avatar", "") or ""
        if res.user_id:
            res.user_link = f"{juejin_constant.JUEJIN_URL}/user/{res.user_id}"
        return res

    # ------------------------------------------------------------------
    # Creator / user info
    # ------------------------------------------------------------------
    def extract_creator(self, json_data: Dict) -> Optional[JuejinCreator]:
        """
        Extract user_api/v1/user/get response.
        Real shape: { err_no, err_msg, data: { user_id, user_name, avatar_large, follower_count, ... } }
        Full fields need login; public response returns profile basics.
        """
        if not json_data:
            return None
        data = json_data.get("data") or {}
        if not data or not data.get("user_id"):
            return None

        res = JuejinCreator()
        res.user_id = str(data.get("user_id"))
        res.user_nickname = data.get("user_name", "") or ""
        res.user_avatar = data.get("avatar_large", "") or data.get("avatar", "") or ""
        res.user_link = f"{juejin_constant.JUEJIN_URL}/user/{res.user_id}"
        res.ip_location = data.get("ip_location", "") or ""
        res.job = data.get("job_title", "") or data.get("job", "") or ""
        res.company = data.get("company", "") or ""
        res.follows = _to_int(data.get("followee_count"))
        res.fans = _to_int(data.get("follower_count"))
        res.got_digg_count = _to_int(data.get("got_digg_count"))
        res.post_article_count = _to_int(data.get("post_article_count"))
        res.level = _to_int(data.get("level"))
        res.description = data.get("description", "") or data.get("brief", "") or ""
        return res

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _fill_author(content: JuejinContent, author: Dict) -> None:
        if not author:
            return
        content.user_id = str(author.get("user_id", "") or "")
        content.user_nickname = author.get("user_name", "") or ""
        content.user_avatar = (
            author.get("avatar_large", "") or author.get("avatar", "") or ""
        )
        if content.user_id:
            content.user_link = f"{juejin_constant.JUEJIN_URL}/user/{content.user_id}"

    @staticmethod
    def _clean_content(content_body: str) -> str:
        """Juejin article content may be HTML or Markdown. Convert to plain text."""
        if not content_body:
            return ""
        # If it looks like HTML, strip tags; otherwise keep markdown text.
        if "<" in content_body and ">" in content_body:
            return extract_text_from_html(content_body)
        # Markdown: just return as-is (plain readable text).
        return content_body


def judge_juejin_url(note_detail_url: str) -> str:
    """
    Judge juejin url type.
    Args:
        note_detail_url: e.g. https://juejin.cn/post/6990140519342932004

    Returns:
        content type string
    """
    if "/post/" in note_detail_url:
        return juejin_constant.ARTICLE_NAME
    return ""
