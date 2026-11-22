"""Browser interface for Smart Capsule.

A dependency-free HTTP server (standard library only) that exposes the same
core engines as the desktop app to a single-page web client, so capsules can be
captured, generated, exported and resumed from a browser.
"""

from webapp.server import create_server, main

__all__ = ["create_server", "main"]
