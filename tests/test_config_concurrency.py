# -*- coding: utf-8 -*-

import config


def test_platform_max_concurrency_uses_platform_override(monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 3)
    monkeypatch.setattr(config, "ZHIHU_MAX_CONCURRENCY_NUM", 10)

    assert config.get_platform_max_concurrency_num("zhihu") == 10


def test_platform_max_concurrency_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 3)
    monkeypatch.setattr(config, "XHS_MAX_CONCURRENCY_NUM", None)

    assert config.get_platform_max_concurrency_num("xhs") == 3


def test_platform_max_concurrency_uses_runtime_default_override(monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 8)
    monkeypatch.setattr(config, "BILI_MAX_CONCURRENCY_NUM", None)

    assert config.get_platform_max_concurrency_num("bili") == 8
