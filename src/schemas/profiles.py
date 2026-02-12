from datetime import date

from fastapi import UploadFile, Form, File
from pydantic import BaseModel, field_validator, ConfigDict

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)


class ProfileCreateSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile

    @classmethod
    def as_form(
        cls,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...)
    ):
        return cls(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
            avatar = avatar
        )

    @field_validator("first_name", "last_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        validate_name(v)
        return v

    @field_validator("gender")
    @classmethod
    def check_gender(cls, v: str) -> str:
        val = v.value if hasattr(v, 'value') else v
        validate_gender(val)
        return val

    @field_validator("date_of_birth")
    @classmethod
    def check_birth_date(cls, v: date) -> date:
        validate_birth_date(v)
        return v

    @field_validator("info")
    @classmethod
    def check_info(cls, v: str) -> str:
        if not v or v.isspace():
            raise ValueError("Info cannot be empty or consist only of spaces.")
        return v

    @field_validator("avatar")
    @classmethod
    def check_avatar(cls, v: UploadFile) -> UploadFile:
        validate_image(v)
        return v


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str

    model_config = ConfigDict(from_attributes=True)
