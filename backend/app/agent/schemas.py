from pydantic import BaseModel

class AgentQuery(BaseModel):
    message: str

class AgentResponse(BaseModel):
    answer: str
    decision: dict
