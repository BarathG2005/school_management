from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from contextlib import asynccontextmanager
import logging

from app.api.v1.endpoints import auth, students, teachers, parents, classes
from app.api.v1.endpoints import admin
from app.api.v1.endpoints import attendance, exams, marks, homework, fees
from app.api.v1.endpoints import timetable, announcements, leave_requests, dashboard
from app.core.config import settings
from app.db.supabase import get_supabase_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting School Management System API...")
    # Test Supabase connection
    try:
        supabase = get_supabase_client()
        logger.info("✓ Supabase connection established")
    except Exception as e:
        logger.error(f"✗ Supabase connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down School Management System API...")

# Initialize FastAPI app
app = FastAPI(
    title="School Management System API",
    description="Complete backend for school administration with role-based access",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }

# Include API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin Management (Master)"])
app.include_router(students.router, prefix="/api/v1/students", tags=["Students"])
app.include_router(teachers.router, prefix="/api/v1/teachers", tags=["Teachers"])
app.include_router(parents.router, prefix="/api/v1/parents", tags=["Parents"])
app.include_router(classes.router, prefix="/api/v1/classes", tags=["Classes"])
app.include_router(attendance.router, prefix="/api/v1/attendance", tags=["Attendance"])
app.include_router(exams.router, prefix="/api/v1/exams", tags=["Exams"])
app.include_router(marks.router, prefix="/api/v1/marks", tags=["Marks"])
app.include_router(homework.router, prefix="/api/v1/homework", tags=["Homework"])
app.include_router(fees.router, prefix="/api/v1/fees", tags=["Fees"])
app.include_router(timetable.router, prefix="/api/v1/timetable", tags=["Timetable"])
app.include_router(announcements.router, prefix="/api/v1/announcements", tags=["Announcements"])
app.include_router(leave_requests.router, prefix="/api/v1/leave-requests", tags=["Leave Requests"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "School Management System API",
        "docs": "/api/docs",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development"
    )