"""Local camera app entry point. Run: python -m app.server"""

from aiohttp import web

from .config import FRONTEND_DIR, HOST, PORT
from .live_bridge import live

ASSETS = {
    "index.html",
    "styles.css",
    "js/app.js",
    "js/audio.js",
    "js/mic-worklet.js",
}


def create_app():
    app = web.Application()

    async def health(request):
        return web.json_response({"status": "ok"})

    async def asset(request):
        name = request.match_info.get("name", "index.html")
        if name not in ASSETS:
            raise web.HTTPNotFound()
        return web.FileResponse(FRONTEND_DIR / name)

    app.router.add_get("/", asset)
    app.router.add_get("/healthz", health)
    app.router.add_get("/live", live)
    app.router.add_get("/{name:.*}", asset)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT, access_log=None)
