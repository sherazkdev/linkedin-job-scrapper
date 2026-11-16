import logging
import traceback
from typing import Any

from pydantic import ValidationError

from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.models.enums import CollectionErrorCategory

logger = logging.getLogger(__name__)


class CollectionErrorHandler:
    @staticmethod
    def categorize(exc: BaseException) -> CollectionErrorCategory:
        if isinstance(exc, ValidationError):
            return CollectionErrorCategory.VALIDATION
        if isinstance(exc, LinkedInCollectionError):
            return CollectionErrorCategory.ADAPTER
        name = exc.__class__.__name__.lower()
        if "timeout" in name or "connection" in name:
            return CollectionErrorCategory.ADAPTER
        if "duplicatekey" in name or "mongo" in name or "database" in name:
            return CollectionErrorCategory.DATABASE
        if "lock" in name:
            return CollectionErrorCategory.LOCK
        if "config" in name or "permission" in name:
            return CollectionErrorCategory.CONFIGURATION
        return CollectionErrorCategory.UNKNOWN

    def record(
        self,
        exc: BaseException,
        *,
        context: dict[str, Any] | None = None,
    ) -> str:
        category = self.categorize(exc)
        if isinstance(exc, LinkedInCollectionError):
            message = f"linkedin:{exc.state.value}"
        else:
            message = f"{category.value}: {exc.__class__.__name__}"
        logger.warning(
            "Collection error category=%s type=%s",
            category.value,
            exc.__class__.__name__,
            extra={"context": context or {}},
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Traceback: %s", traceback.format_exc())
        return message
