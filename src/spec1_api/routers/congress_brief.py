"""Compatibility shim: congress brief routes now live in cls_congress.api.router."""

from cls_congress.api.router import router

__all__ = ["router"]
