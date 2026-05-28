"""Domain exception hierarchy.

Every error the application raises on purpose derives from :class:`AppError`,
which carries an HTTP status, a stable machine-readable ``code`` and a
human-readable message. The API layer turns these into consistent JSON
responses (see ``app.api.errors``).
"""
from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, detail: object = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class DocumentNotFoundError(NotFoundError):
    code = "document_not_found"
    message = "Document not found."


class ConversationNotFoundError(NotFoundError):
    code = "conversation_not_found"
    message = "Conversation not found."


class ValidationError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "The request could not be processed."


class UnsupportedFileTypeError(AppError):
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_file_type"
    message = "Unsupported file type."


class FileTooLargeError(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "file_too_large"
    message = "Uploaded file exceeds the size limit."


class EmptyDocumentError(ValidationError):
    code = "empty_document"
    message = "The document contains no extractable text."


class DocumentParseError(ValidationError):
    code = "document_parse_error"
    message = "The document could not be parsed."


class UpstreamServiceError(AppError):
    status_code = HTTPStatus.BAD_GATEWAY
    code = "upstream_error"
    message = "An upstream service failed."


class EmbeddingServiceError(UpstreamServiceError):
    code = "embedding_service_error"
    message = "The embedding service failed."


class LLMServiceError(UpstreamServiceError):
    code = "llm_service_error"
    message = "The language model service failed."
