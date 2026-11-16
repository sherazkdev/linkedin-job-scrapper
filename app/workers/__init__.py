"""Celery workers, dispatcher, and collection task entry points."""

from app.workers.celery_app import celery_app

__all__ = ["celery_app"]
