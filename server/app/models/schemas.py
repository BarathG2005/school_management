"""
app/models/schemas.py
Fixed Pydantic schemas for the School Management application
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ============================================
# ENUMS
# ============================================

class UserRole(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT = "parent"
    MASTER = "master"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class FeeStatus(str, Enum):
    PAID = "paid"
    PENDING = "pending"
    OVERDUE = "overdue"
    PARTIAL = "partial"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ============================================
# USER & AUTH MODELS
# ============================================

class UserBase(BaseModel):
    email: EmailStr
    role: UserRole
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    user_id: str  # Changed from UUID to str for Supabase
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenPayload(BaseModel):
    sub: str  # Changed from UUID to str
    role: UserRole
    exp: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ============================================
# STUDENT MODELS
# ============================================

class StudentBase(BaseModel):
    name: str
    dob: date
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    guardian_name: Optional[str] = None
    class_id: Optional[str] = None  # Changed from UUID to str


class StudentCreate(StudentBase):
    user_id: Optional[str] = None  # Changed from UUID to str


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    dob: Optional[date] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    guardian_name: Optional[str] = None
    class_id: Optional[str] = None


class StudentResponse(StudentBase):
    student_id: str
    user_id: Optional[str] = None
    class_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# TEACHER MODELS - FIXED
# ============================================

class TeacherBase(BaseModel):
    name: str
    phone: str
    email: EmailStr
    subject_id: Optional[str] = None  # Changed from UUID to str - FIXED
    qualification: Optional[str] = None
    experience_years: Optional[int] = None


class TeacherCreate(TeacherBase):
    user_id: Optional[str] = None  # Changed from UUID to str


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    subject_id: Optional[str] = None  # Changed from UUID to str
    qualification: Optional[str] = None
    experience_years: Optional[int] = None


class TeacherResponse(TeacherBase):
    teacher_id: str
    user_id: Optional[str] = None
    subject_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# PARENT MODELS - FIXED
# ============================================

class ParentBase(BaseModel):
    name: str
    phone: str
    email: EmailStr
    occupation: Optional[str] = None


class ParentCreate(ParentBase):
    user_id: Optional[str] = None
    student_ids: List[str] = []  # Fixed: was children_ids


class ParentResponse(ParentBase):
    parent_id: str
    user_id: Optional[str] = None
    students: List[StudentResponse] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# CLASS MODELS
# ============================================

class ClassBase(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=50)
    section: str = Field(..., min_length=1, max_length=10)
    academic_year: str
    teacher_id: Optional[str] = None


class ClassCreate(ClassBase):
    pass


class ClassResponse(ClassBase):
    class_id: str
    teacher_name: Optional[str] = None
    student_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# SUBJECT MODELS
# ============================================

class SubjectBase(BaseModel):
    subject_name: str = Field(..., min_length=2, max_length=100)
    class_id: str
    code: Optional[str] = None


class SubjectCreate(SubjectBase):
    pass


class SubjectResponse(SubjectBase):
    subject_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# ATTENDANCE MODELS
# ============================================

class AttendanceBase(BaseModel):
    student_id: str
    date: date
    status: AttendanceStatus
    remarks: Optional[str] = None


class AttendanceCreate(AttendanceBase):
    pass


class AttendanceBulkCreate(BaseModel):
    class_id: str
    date: date
    attendance_records: List[Dict[str, Any]]


class AttendanceResponse(AttendanceBase):
    attendance_id: str
    student_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# EXAM MODELS
# ============================================

class ExamBase(BaseModel):
    class_id: str
    subject_id: str
    exam_name: str
    date: date
    max_marks: int = Field(..., gt=0)
    duration_minutes: Optional[int] = None

class ExamUpdate(BaseModel):
    class_id: Optional[str] = None
    subject_id: Optional[str] = None
    exam_name: Optional[str] = None
    date: Optional[date] = None
    max_marks: Optional[int] = None
    duration_minutes: Optional[int] = None

class ExamCreate(ExamBase):
    pass


class ExamResponse(ExamBase):
    exam_id: str
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# MARKS MODELS
# ============================================

class MarksBase(BaseModel):
    exam_id: str
    student_id: str
    marks_scored: float = Field(..., ge=0)
    remarks: Optional[str] = None


class MarksCreate(MarksBase):
    pass

class MarksUpdate(BaseModel):
    marks_scored: Optional[float] = Field(None, ge=0)
    remarks: Optional[str] = None

class MarksResponse(MarksBase):
    mark_id: str
    student_name: Optional[str] = None
    exam_name: Optional[str] = None
    max_marks: Optional[int] = None
    percentage: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# HOMEWORK MODELS
# ============================================

class HomeworkBase(BaseModel):
    class_id: str
    teacher_id: str
    subject_id: str
    description: str
    due_date: date
    attachments: Optional[List[str]] = []

class HomeworkUpdate(BaseModel):
    class_id: Optional[str] = None
    teacher_id: Optional[str] = None
    subject_id: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    attachments: Optional[List[str]] = None

class HomeworkCreate(HomeworkBase):
    pass


class HomeworkResponse(HomeworkBase):
    hw_id: str
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# SUBMISSION MODELS
# ============================================

class SubmissionBase(BaseModel):
    student_id: str
    hw_id: str
    file_link: Optional[str] = None
    text_content: Optional[str] = None
    submitted_date: datetime = Field(default_factory=datetime.now)


class SubmissionCreate(SubmissionBase):
    pass


class SubmissionResponse(SubmissionBase):
    submission_id: str
    student_name: Optional[str] = None
    homework_description: Optional[str] = None
    grade: Optional[str] = None
    feedback: Optional[str] = None

    model_config = {"from_attributes": True}


# ============================================
# FEE MODELS
# ============================================

class FeeBase(BaseModel):
    student_id: str
    amount: float = Field(..., gt=0)
    fee_type: str
    due_date: date
    status: FeeStatus = FeeStatus.PENDING
    academic_year: str


class FeeCreate(FeeBase):
    pass

class FeeUpdate(BaseModel):
    student_id: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    fee_type: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[FeeStatus] = None
    academic_year: Optional[str] = None

class FeePayment(BaseModel):
    fee_id: str
    amount_paid: float = Field(..., gt=0)
    payment_method: str
    transaction_id: Optional[str] = None


class FeeResponse(FeeBase):
    fee_id: str
    student_name: Optional[str] = None
    amount_paid: float = 0
    balance: float = 0
    payment_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# TIMETABLE MODELS
# ============================================

class TimetableBase(BaseModel):
    class_id: str
    day: str
    period_number: int
    subject_id: str
    teacher_id: str
    start_time: str
    end_time: str


class TimetableCreate(TimetableBase):
    pass


class TimetableUpdate(BaseModel):
    class_id: Optional[str] = None
    day: Optional[str] = None
    period_number: Optional[int] = None
    subject_id: Optional[str] = None
    teacher_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class TimetableResponse(TimetableBase):
    timetable_id: str
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ============================================
# ANNOUNCEMENT MODELS
# ============================================

class AnnouncementBase(BaseModel):
    teacher_id: str
    title: str
    message: str
    target_audience: str
    class_id: Optional[str] = None
    is_urgent: bool = False

class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    target_audience: Optional[str] = None
    class_id: Optional[str] = None
    is_urgent: Optional[bool] = None

class AnnouncementCreate(AnnouncementBase):
    pass


class AnnouncementResponse(AnnouncementBase):
    announcement_id: str
    teacher_name: Optional[str] = None
    date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# LEAVE REQUEST MODELS
# ============================================

class LeaveRequestBase(BaseModel):
    student_id: str
    start_date: date
    end_date: date
    reason: str
    status: LeaveStatus = LeaveStatus.PENDING


class LeaveRequestCreate(LeaveRequestBase):
    pass


class LeaveRequestUpdate(BaseModel):
    status: LeaveStatus
    admin_remarks: Optional[str] = None


class LeaveRequestResponse(LeaveRequestBase):
    request_id: str
    student_name: Optional[str] = None
    admin_remarks: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================
# PAGINATION
# ============================================

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    data: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================
# DASHBOARD
# ============================================

class DashboardSummary(BaseModel):
    total_students: int = 0
    total_teachers: int = 0
    total_classes: int = 0
    pending_leave_requests: int = 0


# ============================================
# EXPORTS
# ============================================

__all__ = [
    # Enums
    "UserRole",
    "AttendanceStatus",
    "FeeStatus",
    "LeaveStatus",
    # User & Auth
    "UserBase",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "TokenPayload",
    "Token",
    # Student
    "StudentBase",
    "StudentCreate",
    "StudentUpdate",
    "StudentResponse",
    # Teacher
    "TeacherBase",
    "TeacherCreate",
    "TeacherUpdate",
    "TeacherResponse",
    # Parent
    "ParentBase",
    "ParentCreate",
    "ParentResponse",
    # Class
    "ClassBase",
    "ClassCreate",
    "ClassResponse",
    # Subject
    "SubjectBase",
    "SubjectCreate",
    "SubjectResponse",
    # Attendance
    "AttendanceBase",
    "AttendanceCreate",
    "AttendanceBulkCreate",
    "AttendanceResponse",
    # Exam
    "ExamBase",
    "ExamCreate",
    "ExamResponse",
    # Marks
    "MarksBase",
    "MarksCreate",
    "MarksResponse",
    # Homework
    "HomeworkBase",
    "HomeworkCreate",
    "HomeworkResponse",
    # Submission
    "SubmissionBase",
    "SubmissionCreate",
    "SubmissionResponse",
    # Fee
    "FeeBase",
    "FeeCreate",
    "FeePayment",
    "FeeResponse",
    # Timetable
    "TimetableBase",
    "TimetableCreate",
    "TimetableResponse",
    # Announcement
    "AnnouncementBase",
    "AnnouncementCreate",
    "AnnouncementResponse",
    # Leave Request
    "LeaveRequestBase",
    "LeaveRequestCreate",
    "LeaveRequestUpdate",
    "LeaveRequestResponse",
    # Pagination
    "PaginationParams",
    "PaginatedResponse",
    # Dashboard
    "DashboardSummary",
]