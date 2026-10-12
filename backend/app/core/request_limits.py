"""Rejects oversized request bodies before any parsing happens."""
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware:
    def __init__(self, app, default_limit: int, bulk_limit: int):
        self.app = app
        self.default_limit = default_limit
        self.bulk_limit = bulk_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        limit = self.bulk_limit if path.endswith(("/bulk", "/bulk-upload")) else self.default_limit
        raw = dict(scope["headers"]).get(b"content-length")

        if raw is None:
            response = JSONResponse({"detail": "Content-Length header is required."}, status_code=411)
            await response(scope, receive, send)
            return
        try:
            too_big = int(raw) > limit
        except ValueError:
            too_big = True
        if too_big:
            response = JSONResponse({"detail": "Request body too large."}, status_code=413)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)