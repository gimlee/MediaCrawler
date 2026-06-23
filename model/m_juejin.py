# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/model/m_juejin.py
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
from typing import Optional

from pydantic import BaseModel, Field


class JuejinContent(BaseModel):
    """
    Juejin article content
    """
    content_id: str = Field(default="", description="Content ID (article_id)")
    content_type: str = Field(default="article", description="Content type, fixed to article for now")
    content_text: str = Field(default="", description="Content text (markdown/html body converted to text)")
    content_url: str = Field(default="", description="Content landing page URL")
    title: str = Field(default="", description="Content title")
    desc: str = Field(default="", description="Content description / brief")
    created_time: int = Field(default=0, description="Create time (seconds timestamp)")
    updated_time: int = Field(default=0, description="Update time (seconds timestamp)")
    view_count: int = Field(default=0, description="View count")
    digg_count: int = Field(default=0, description="Like (digg) count")
    comment_count: int = Field(default=0, description="Comment count")
    collect_count: int = Field(default=0, description="Collect (favorite) count")
    share_count: int = Field(default=0, description="Share count")
    category_name: str = Field(default="", description="Category name")
    source_keyword: str = Field(default="", description="Source keyword")

    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar URL")


class JuejinComment(BaseModel):
    """
    Juejin comment
    """

    comment_id: str = Field(default="", description="Comment ID")
    parent_comment_id: str = Field(default="", description="Parent comment ID")
    content: str = Field(default="", description="Comment content")
    publish_time: int = Field(default=0, description="Publish time (seconds timestamp)")
    sub_comment_count: int = Field(default=0, description="Sub-comment (reply) count")
    like_count: int = Field(default=0, description="Like (digg) count")
    content_id: str = Field(default="", description="Content ID (article_id)")

    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar URL")


class JuejinCreator(BaseModel):
    """
    Juejin creator
    """
    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar URL")
    ip_location: Optional[str] = Field(default="", description="IP location")
    job: str = Field(default="", description="Job / position")
    company: str = Field(default="", description="Company")
    follows: int = Field(default=0, description="Follows count (followee)")
    fans: int = Field(default=0, description="Fans count (follower)")
    got_digg_count: int = Field(default=0, description="Total got like count")
    post_article_count: int = Field(default=0, description="Post article count")
    level: int = Field(default=0, description="User level")
    description: str = Field(default="", description="User description")
