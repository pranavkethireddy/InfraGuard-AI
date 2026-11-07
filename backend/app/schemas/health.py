from typing import Literal

from .common import ContractModel


class HealthDependencies(ContractModel):
    database: str
    models: dict[str, Literal["available", "unavailable"]]
    retrieval: str


class HealthResponse(ContractModel):
    status: Literal["ok", "degraded"]
    contract_version: str
    version: str
    dependencies: HealthDependencies
