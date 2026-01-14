from fastapi import FastAPI
from app.agent.router import router as agent_router
from app.mcp.server import router as mcp_router
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

app.include_router(agent_router, prefix="/agent")
app.include_router(mcp_router)
@app.get("/")
def root():
    return {"message": "Backend is running"}
