from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.files import router as files_router
from app.api.routers.health import router as health_router
from app.core.config import settings
from app.core.exceptions import GeospatialAPIException

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(GeospatialAPIException)
async def geospatial_exception_handler(request: Request, exc: GeospatialAPIException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "detail": exc.detail,
        },
    )


# Include Routers under /api
app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(files_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "endpoints": {
            "upload": f"POST {settings.API_PREFIX}/files/",
            "list_files": f"GET {settings.API_PREFIX}/files/",
            "file_info": f"GET {settings.API_PREFIX}/files/{{id}}/",
            "measurements": f"GET {settings.API_PREFIX}/files/{{id}}/measurements/",
            "features": f"GET {settings.API_PREFIX}/files/{{id}}/features/",
            "health": f"GET {settings.API_PREFIX}/health",
        },
    }

