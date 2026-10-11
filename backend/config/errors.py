from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_handler


def exception_handler(exc, context):
    """Every error leaves the API as {code, message, fields}."""
    response = drf_handler(exc, context)
    if response is None:
        return None
    data = response.data
    fields = {}
    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Validation failed."
        if isinstance(data, dict):
            fields = {k: (v if isinstance(v, list) else [v]) for k, v in data.items()}
            if "detail" in fields:
                message = str(fields.pop("detail")[0])
        elif isinstance(data, list) and data:
            message = str(data[0])
    else:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else "error"
        code = codes if isinstance(codes, str) else "error"
        message = str(data.get("detail", "")) if isinstance(data, dict) else str(data)
    response.data = {"code": code, "message": message, "fields": fields}
    return response
