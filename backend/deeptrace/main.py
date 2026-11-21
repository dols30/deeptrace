from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deeptrace.api import router
from deeptrace.config import settings
from deeptrace.workflow.routes import router as workflow_router

app = FastAPI(title=settings.app_name, version="0.2.0",
    description="Advisory-only audio/video authenticity screening proof of concept.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
app.include_router(workflow_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
