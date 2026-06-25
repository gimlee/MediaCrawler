from fastapi.testclient import TestClient

from api.main import app
from api.schemas import CrawlerStartRequest, PlatformEnum
from api.services.crawler_manager import CrawlerManager


def test_api_schema_accepts_juejin_and_builds_cli_command():
    request = CrawlerStartRequest(
        platform="juejin",
        crawler_type="detail",
        specified_ids="6990140519342932004",
    )

    assert request.platform is PlatformEnum.JUEJIN
    command = CrawlerManager()._build_command(request)
    assert command[command.index("--platform") + 1] == "juejin"
    assert command[command.index("--specified_id") + 1] == "6990140519342932004"


def test_webui_platform_endpoint_contains_juejin():
    response = TestClient(app).get("/api/config/platforms")

    assert response.status_code == 200
    assert {
        "value": "juejin",
        "label": "Juejin",
        "icon": "code-2",
    } in response.json()["platforms"]


def test_data_stats_recognizes_juejin(tmp_path, monkeypatch):
    from api.routers import data

    platform_dir = tmp_path / "juejin"
    platform_dir.mkdir()
    (platform_dir / "juejin_search_contents.json").write_text(
        "[]",
        encoding="utf-8",
    )
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)

    response = TestClient(app).get("/api/data/stats")

    assert response.json()["by_platform"]["juejin"] == 1
