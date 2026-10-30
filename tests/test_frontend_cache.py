"""The Studio shell is always revalidated, so an update never leaves an old build running."""

from pathlib import Path

from fastapi.testclient import TestClient

from mp3_to_videoclip.app import create_app

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def test_the_shell_is_revalidated_and_hashed_assets_are_immutable(tmp_path):
    asset = next((DIST / "assets").glob("index-*.js")).name
    with TestClient(create_app(projects_dir=tmp_path), base_url="http://127.0.0.1") as client:
        for path in ("/", "/index.html"):
            shell = client.get(path)
            assert shell.status_code == 200
            assert shell.headers["cache-control"] == "no-cache"
            assert shell.headers["etag"]
            again = client.get(path, headers={"if-none-match": shell.headers["etag"]})
            assert again.status_code == 304
            assert again.headers["cache-control"] == "no-cache"
        built = client.get(f"/assets/{asset}")
        assert built.status_code == 200
        assert built.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/api/health").headers.get("cache-control") != "no-cache"
