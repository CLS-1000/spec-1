"""Standalone API surface for the Congress Brief product."""

from cls_congress.api.main import app, create_app
from cls_congress.api.router import router

__all__ = ["app", "create_app", "router"]
