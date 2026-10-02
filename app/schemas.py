import base64
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

Modality = Literal['CE', 'NCE', 'PET_CT', 'PATH']

class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    modality: Modality
    name: str = Field(default='报告文本', max_length=180)
    text: str = Field(default='', max_length=60000)
    file_base64: str = Field(default='', max_length=15_000_000)
    force_ocr: bool = False

    @model_validator(mode='after')
    def one_source(self):
        if bool(self.text.strip()) == bool(self.file_base64):
            raise ValueError('每份报告请选择文字或文件之一。')
        return self

    def bytes(self):
        try:
            result = base64.b64decode(self.file_base64, validate=True)
        except Exception:
            raise ValueError('文件Base64无效。')
        if len(result) > 10 * 1024 * 1024:
            raise ValueError('单文件不得超过10MB。')
        return result

class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_label: str = Field(default='研究病例', max_length=80)
    reports: list[ReportInput] = Field(min_length=1, max_length=8)

class PredictInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis_id: str = Field(max_length=64)
    revision: int = Field(ge=1)
    edits: dict[str, float | int | None] = Field(default_factory=dict, max_length=400)
    review_confirmed: bool = False
    scope_confirmed: bool = False
