import asyncio
import pathlib
import sys
import unittest

from starlette.requests import Request
from starlette.responses import JSONResponse


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def make_request(path):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("203.0.113.10", 12345),
            "server": ("0.0.0.0", 8000),
            "scheme": "http",
        }
    )


async def ok_response(_request):
    return JSONResponse({"ok": True})


class ApiAuthMiddlewareTests(unittest.TestCase):
    def with_auth_globals(self, server, *, api_key, desktop_mode):
        original = {
            "_API_KEY": server._API_KEY,
            "_AUTHLESS_DESKTOP_MODE": server._AUTHLESS_DESKTOP_MODE,
        }
        server._API_KEY = api_key
        server._AUTHLESS_DESKTOP_MODE = desktop_mode
        return original

    def restore_auth_globals(self, server, original):
        server._API_KEY = original["_API_KEY"]
        server._AUTHLESS_DESKTOP_MODE = original["_AUTHLESS_DESKTOP_MODE"]

    def test_unkeyed_non_local_bind_rejects_protected_api(self):
        import server

        middleware = server.APIKeyMiddleware(lambda scope, receive, send: None)
        original = self.with_auth_globals(server, api_key="", desktop_mode=False)
        try:
            response = asyncio.run(
                middleware.dispatch(make_request("/api/settings"), ok_response)
            )
        finally:
            self.restore_auth_globals(server, original)

        self.assertEqual(response.status_code, 503)

    def test_unkeyed_local_desktop_mode_allows_protected_api(self):
        import server

        middleware = server.APIKeyMiddleware(lambda scope, receive, send: None)
        original = self.with_auth_globals(server, api_key="", desktop_mode=True)
        try:
            response = asyncio.run(
                middleware.dispatch(make_request("/api/settings"), ok_response)
            )
        finally:
            self.restore_auth_globals(server, original)

        self.assertEqual(response.status_code, 200)

    def test_health_endpoint_is_public_without_key(self):
        import server

        middleware = server.APIKeyMiddleware(lambda scope, receive, send: None)
        original = self.with_auth_globals(server, api_key="", desktop_mode=False)
        try:
            response = asyncio.run(
                middleware.dispatch(make_request("/api/health"), ok_response)
            )
        finally:
            self.restore_auth_globals(server, original)

        self.assertEqual(response.status_code, 200)

    def test_pairing_status_endpoint_is_public_without_key(self):
        import server

        middleware = server.APIKeyMiddleware(lambda scope, receive, send: None)
        original = self.with_auth_globals(server, api_key="", desktop_mode=False)
        try:
            response = asyncio.run(
                middleware.dispatch(make_request("/api/pairing/status"), ok_response)
            )
        finally:
            self.restore_auth_globals(server, original)

        self.assertEqual(response.status_code, 200)

    def test_production_mode_without_api_key_is_invalid_even_for_local_sqlite(self):
        import server

        with self.assertRaises(RuntimeError):
            server.validate_api_auth_startup(
                api_key="",
                use_sqlite=True,
                bind_host="127.0.0.1",
                app_env="production",
            )

    def test_local_sqlite_desktop_mode_without_api_key_is_allowed_outside_production(self):
        import server

        result = server.validate_api_auth_startup(
            api_key="",
            use_sqlite=True,
            bind_host="127.0.0.1",
            app_env="development",
        )

        self.assertTrue(result["authless_desktop_mode"])


if __name__ == "__main__":
    unittest.main()
