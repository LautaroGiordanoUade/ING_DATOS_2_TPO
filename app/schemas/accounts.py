from pydantic import BaseModel, ConfigDict, Field


class AccountDecision(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={"examples": [{"reason": "Incumplimiento confirmado de las reglas"}]},
    )
    reason: str = Field(min_length=1, max_length=1000)
