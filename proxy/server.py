"""
Claude Code Proxy Server

A proxy server that provides controlled access to external services
with credential management and configurable restrictions.

Security:
- Designed to run on an internal Docker network (not exposed to host)
- Optional shared-secret authentication via X-Proxy-Auth header
- Health endpoint is always accessible (for Docker healthchecks)
"""

import hashlib
import hmac
import importlib
import pkgutil
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
import tools


# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate requests using shared secret."""

    # Endpoints that don't require authentication
    PUBLIC_PATHS = {"/health", "/"}

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth if no secret is configured or auth is disabled
        if not settings.auth_secret or not settings.auth_required:
            return await call_next(request)

        # Check for auth header
        auth_header = request.headers.get("X-Proxy-Auth", "")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "AUTHENTICATION_REQUIRED",
                    "message": "Missing X-Proxy-Auth header",
                },
            )

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(auth_header, settings.auth_secret):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "AUTHENTICATION_FAILED",
                    "message": "Invalid authentication token",
                },
            )

        return await call_next(request)


app = FastAPI(
    title="Claude Code Proxy",
    description="Proxy server for Claude Code container with credential management and access controls",
    version="1.1.0",
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)


def discover_tools() -> dict[str, Any]:
    """Discover and load all available tools from the tools package."""
    discovered = {}
    tools_path = Path(__file__).parent / "tools"

    for _, name, _ in pkgutil.iter_modules([str(tools_path)]):
        if name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"tools.{name}")
            if hasattr(module, "router"):
                discovered[name] = {
                    "router": module.router,
                    "info": getattr(module, "TOOL_INFO", {"name": name, "description": "No description"}),
                }
        except Exception as e:
            print(f"Warning: Failed to load tool '{name}': {e}")

    return discovered


# Discover and register tools
registered_tools = discover_tools()
for tool_name, tool_data in registered_tools.items():
    app.include_router(tool_data["router"], prefix=f"/{tool_name}", tags=[tool_name])


@app.get("/")
async def root():
    """Root endpoint with proxy information."""
    return {
        "service": "Claude Code Proxy",
        "version": "1.0.0",
        "endpoints": {
            "tools": "/tools - List available tools",
            "health": "/health - Health check",
            "tool_access": "/<tool-name>/ - Access specific tool endpoints",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (always accessible, no auth required)."""
    return {
        "status": "healthy",
        "tools_loaded": list(registered_tools.keys()),
        "auth_enabled": bool(settings.auth_secret and settings.auth_required),
    }


@app.get("/tools")
async def list_tools():
    """List all available tools and their endpoints."""
    tools_info = {}
    for tool_name, tool_data in registered_tools.items():
        info = tool_data["info"].copy()
        # Get routes from the router
        routes = []
        for route in tool_data["router"].routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append({
                    "path": f"/{tool_name}{route.path}",
                    "methods": list(route.methods - {"HEAD", "OPTIONS"}) if route.methods else ["GET"],
                    "description": route.description if hasattr(route, "description") else route.name,
                })
        info["endpoints"] = routes
        tools_info[tool_name] = info

    return {
        "available_tools": tools_info,
        "usage": "Access tools via /<tool-name>/<action>",
    }


@app.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get detailed information about a specific tool."""
    if tool_name not in registered_tools:
        return JSONResponse(
            status_code=404,
            content={"error": f"Tool '{tool_name}' not found", "available": list(registered_tools.keys())},
        )

    tool_data = registered_tools[tool_name]
    info = tool_data["info"].copy()

    # Get detailed route information
    routes = []
    for route in tool_data["router"].routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            route_info = {
                "path": f"/{tool_name}{route.path}",
                "methods": list(route.methods - {"HEAD", "OPTIONS"}) if route.methods else ["GET"],
                "name": route.name if hasattr(route, "name") else None,
            }
            # Try to get docstring
            if hasattr(route, "endpoint") and route.endpoint.__doc__:
                route_info["description"] = route.endpoint.__doc__.strip()
            routes.append(route_info)

    info["endpoints"] = routes
    return info


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
