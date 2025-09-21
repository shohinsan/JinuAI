"""Error Handling Utilities
========================
Standardizes API error responses by mapping validation errors
to uniform error codes and formatting HTTP exceptions for consistent JSON output.
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def get_error_key(error_type: str, error_msg: str = "") -> str:
    """Get standardized error key based on Pydantic error type."""
    # Direct mapping for common types
    type_map = {
        # String validations
        "string_type": "MUST_BE_STRING",
        "string_too_short": "TOO_SHORT",
        "string_too_long": "TOO_LONG",
        "string_pattern_mismatch": "INVALID_FORMAT",
        # Number validations
        "int_type": "MUST_BE_INTEGER",
        "float_type": "MUST_BE_NUMBER",
        "greater_than": "TOO_SMALL",
        "less_than": "TOO_LARGE",
        # Boolean
        "bool_type": "MUST_BE_BOOLEAN",
        # Collections
        "list_type": "MUST_BE_LIST",
        "dict_type": "MUST_BE_OBJECT",
        "too_short": "TOO_FEW_ITEMS",
        "too_long": "TOO_MANY_ITEMS",
        # Common validations
        "missing": "REQUIRED",
        "extra_forbidden": "NOT_ALLOWED",
        "literal_error": "INVALID_CHOICE",
        "enum_error": "INVALID_CHOICE",
    }

    # Check direct mapping first
    if error_type in type_map:
        return type_map[error_type]

    # Handle special cases
    if error_type == "value_error":
        msg_lower = error_msg.lower()
        if "email" in msg_lower:
            return "INVALID_EMAIL"
        elif "url" in msg_lower:
            return "INVALID_URL"
        elif "uuid" in msg_lower:
            return "INVALID_UUID"
        elif "datetime" in msg_lower or "date" in msg_lower:
            return "INVALID_DATE"
        return "INVALID_VALUE"

    # Fallback for unmapped types
    return "INVALID"


def format_field_path(location: tuple) -> str:
    if not location:
        return "unknown"

    # Handle nested field paths
    path_parts = []
    for part in location:
        if isinstance(part, str):
            path_parts.append(part)
        elif isinstance(part, int):
            path_parts.append(f"[{part}]")

    return ".".join(path_parts) if path_parts else str(location[-1])


async def validation_exception_handler(
    request: Request, exc: RequestValidationError | ValidationError
):
    errors = {}

    for error in exc.errors():
        field_path = format_field_path(error.get("loc", ()))
        error_type = error.get("type", "")
        error_msg = error.get("msg", "")

        error_key = get_error_key(error_type, error_msg)

        # Create standardized error code
        field_name = field_path.split(".")[0].upper()
        errors[field_path] = f"VALIDATION_{field_name}_{error_key}"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"errors": errors}
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content={"errors": exc.detail})

    detail = str(exc.detail).strip().rstrip(".!?,")
    error_code = detail.replace(" ", "_").upper()

    return JSONResponse(status_code=exc.status_code, content={"errors": error_code})


request_validation_error = validation_exception_handler
validation_error = validation_exception_handler
http_validation_error = http_exception_handler