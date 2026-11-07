from typing import Any

from .common import ContractModel


class ErrorBody(ContractModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: str


class ErrorResponse(ContractModel):
    error: ErrorBody
