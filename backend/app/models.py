"""Typed public API contracts."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Coordinates(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)


class ResolveRequest(BaseModel):
    name: str | None = Field(default=None, max_length=130)
    ra: str | float | None = None
    dec: str | float | None = None
    epoch: str | None = None
    category: str = 'all'

    @model_validator(mode='after')
    def require_target(self):
        if not self.name and (self.ra is None or self.dec is None):
            raise ValueError('Provide an object name or both coordinates.')
        return self


class SearchRequest(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(default=10, ge=1, le=30)
    collections: list[str] = Field(default_factory=lambda: ['spherex_dr1', 'spherex_qr3'], min_length=1, max_length=4)
    detector: int | None = Field(default=None, ge=1, le=6)
    max_records: int = Field(default=36, ge=1, le=120)
    date_from: str | None = None
    date_to: str | None = None

    @field_validator('collections')
    @classmethod
    def valid_collections(cls, values):
        from .settings import COLLECTIONS
        if any(c not in COLLECTIONS for c in values):
            raise ValueError('Only known SPHEREx collections are allowed.')
        return list(dict.fromkeys(values))

    @field_validator('date_from', 'date_to')
    @classmethod
    def valid_dates(cls, value):
        if value:
            datetime.strptime(value, '%Y-%m-%d')
        return value


class FrameRequest(BaseModel):
    observation: dict
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(default=10, ge=1, le=30)


class CompareRequest(BaseModel):
    frame_a: str = Field(min_length=20, max_length=100)
    frame_b: str = Field(min_length=20, max_length=100)
    method: Literal['difference', 'stack'] = 'difference'


class AnnotationRequest(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    target: str = Field(default='Unknown target', max_length=130)
    frame_id: str = Field(min_length=20, max_length=100)
    note: str = Field(min_length=3, max_length=800)
    kind: Literal['motion', 'brightness', 'artifact', 'other'] = 'other'


class ExoplanetQuery(BaseModel):
    q: str = Field(default='', max_length=70)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)


class LightCurveRequest(BaseModel):
    frame_ids: list[str] = Field(min_length=2, max_length=20)
    radius_pixels: float = Field(default=3.0, ge=1.5, le=8.0)

    @field_validator('frame_ids')
    @classmethod
    def unique_frames(cls, frames):
        if len(frames) != len(set(frames)):
            raise ValueError('Duplicate frames are not independent photometric observations.')
        if any(len(x) != 64 for x in frames):
            raise ValueError('Frame IDs must be 64-character hashes.')
        return frames


class AnnualCompareRequest(BaseModel):
    """Comparison selects only real SIA records previously returned to this client."""
    search_request_id: str = Field(min_length=20, max_length=64)
    year_a: int = Field(ge=2020, le=2100)
    year_b: int = Field(ge=2020, le=2100)
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(default=10, ge=1, le=30)

    @model_validator(mode='after')
    def different_years(self):
        if self.year_a == self.year_b:
            raise ValueError('Select two different observing years.')
        return self
