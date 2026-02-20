from pydantic import BaseModel


class PaginationParams(BaseModel):
    skip: int = 0
    limit: int = 50


class MessageResponse(BaseModel):
    message: str
