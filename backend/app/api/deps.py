from typing import Annotated

from fastapi import Depends, Request

from ..core.config import Settings, get_settings
from ..services.store import Store


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
