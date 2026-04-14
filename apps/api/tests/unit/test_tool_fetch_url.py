from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.unit
async def test_fetch_url_returns_body() -> None:
    mock_resp = AsyncMock()
    mock_resp.text = "hello"
    mock_resp.status_code = 200
    mock_resp.url = "http://example.com/"
    mock_resp.raise_for_status = lambda: None

    with patch("app.tools.fetch_url.httpx.AsyncClient") as mock_ctor:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_ctor.return_value.__aenter__.return_value = mock_client

        from app.tools.fetch_url import fetch_url

        result = await fetch_url.ainvoke({"url": "http://example.com/"})

    assert result["status"] == 200
    assert result["text"] == "hello"


@pytest.mark.unit
async def test_fetch_url_returns_error_on_exception() -> None:
    with patch("app.tools.fetch_url.httpx.AsyncClient") as mock_ctor:
        mock_ctor.return_value.__aenter__.side_effect = httpx.ConnectError("dns")
        from app.tools.fetch_url import fetch_url

        result = await fetch_url.ainvoke({"url": "http://bad"})
    assert "error" in result
    assert "dns" in result["error"]
