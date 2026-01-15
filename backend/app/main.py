from fastapi import FastAPI
from app.agent.router import router as agent_router
from app.mcp.server import router as mcp_router
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router, prefix="/agent")
app.include_router(mcp_router)
@app.get("/")
def root():
    return {"message": "Backend is running"}
