from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID

class CurrencyReport(BaseModel):
    datetime: str
    currency:str
    value: float
    

    