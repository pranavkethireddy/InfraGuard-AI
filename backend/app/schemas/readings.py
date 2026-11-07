from pydantic import AwareDatetime, Field

from .common import ContractModel, DataOrigin, ReadingValue


class Reading(ContractModel):
    observed_at: AwareDatetime
    values: dict[str, ReadingValue] = Field(min_length=1)


class ReadingsRequest(ContractModel):
    asset_id: str
    data_origin: DataOrigin
    simulation_id: str | None = None
    readings: list[Reading] = Field(min_length=1, max_length=1000)


class ReadingsResponse(ContractModel):
    asset_id: str
    accepted: int = Field(ge=0)


class StoredReading(Reading):
    data_origin: DataOrigin


class AssetReadingsResponse(ContractModel):
    asset_id: str
    start: AwareDatetime
    end: AwareDatetime
    items: list[StoredReading]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=2000)
