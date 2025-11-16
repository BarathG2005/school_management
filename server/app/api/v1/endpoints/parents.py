"""
app/api/v1/endpoints/parents.py
Parent management endpoints with auto user creation
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.models.schemas import ParentCreate, ParentResponse, TokenPayload, StudentResponse
from app.core.security import require_admin, require_parent, get_current_user, hash_password
from app.db.supabase import get_supabase_client, SupabaseQueries
# from app.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
# email_service = EmailService()

@router.post("/", response_model=ParentResponse, status_code=status.HTTP_201_CREATED)
async def create_parent(
    parent_data: ParentCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a new parent (Admin only)
    Also creates a user account with phone number as password
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Validate required fields
        if not parent_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required to create parent account"
            )
        
        if not parent_data.phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required (used as temporary password)"
            )
        
        # Check if email already exists in parents table
        existing_parent = await db.select_all("parents", {"email": parent_data.email})
        if existing_parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent with this email already exists"
            )
        
        # Check if email already exists in users table
        existing_user = await db.select_all("users", {"email": parent_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Step 1: Create user account with phone as password
        user_data = {
            "email": parent_data.email,
            "password_hash": hash_password(parent_data.phone),
            "role": "parent",
            "is_active": True
        }
        
        new_user = await db.insert_one("users", user_data)
        logger.info(f"User account created for parent: {new_user['user_id']}")
        
        # Step 2: Create parent record
        parent_dict = parent_data.model_dump(exclude={"student_ids"})
        parent_dict["user_id"] = new_user["user_id"]  # Link to user account
        
        new_parent = await db.insert_one("parents", parent_dict)
        
        # Step 3: Link parent to students
        linked_students = []
        if parent_data.student_ids:
            for student_id in parent_data.student_ids:
                # Verify student exists
                student = await db.select_by_id("students", "student_id", student_id)
                if not student:
                    logger.warning(f"Student {student_id} not found, skipping link")
                    continue
                
                # Create parent-student relationship
                await db.insert_one("parent_student", {
                    "parent_id": new_parent["parent_id"],
                    "student_id": student_id,
                    "relationship": "Guardian"
                })
                
                linked_students.append(student)
        
        # Send welcome email
        try:
            student_names = ", ".join([s["name"] for s in linked_students]) if linked_students else "will be assigned"
            
            await email_service.send_email(
                to_email=parent_data.email,
                subject="Welcome to School Management System",
                html_content=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #1976D2;">👪 Welcome to Our School Community!</h2>
                    <p>Dear {parent_data.name},</p>
                    <p>Your parent account has been created successfully.</p>
                    
                    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Your Login Credentials:</h3>
                        <p><strong>Email:</strong> {parent_data.email}</p>
                        <p><strong>Temporary Password:</strong> {parent_data.phone}</p>
                    </div>
                    
                    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Your Children:</h3>
                        <p>{student_names}</p>
                    </div>
                    
                    <p><strong style="color: #d32f2f;">IMPORTANT:</strong> Please change your password immediately after your first login for security reasons.</p>
                    
                    <p>As a parent, you can:</p>
                    <ul>
                        <li>View your children's attendance</li>
                        <li>Check academic performance</li>
                        <li>View exam results</li>
                        <li>Submit leave requests</li>
                        <li>View fee status</li>
                        <li>Communicate with teachers</li>
                    </ul>
                    
                    <p>You can login at: <a href="http://localhost:8000/api/docs">Parent Portal</a></p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">
                        This is an automated email. Please do not reply.
                    </p>
                </div>
                """
            )
            logger.info(f"Welcome email sent to {parent_data.email}")
        except Exception as email_error:
            logger.warning(f"Failed to send welcome email: {email_error}")
        
        logger.info(f"Parent created: {new_parent['parent_id']}")
        
        # Get linked students with full details
        students_response = []
        for student in linked_students:
            students_response.append(StudentResponse(**student))
        
        return ParentResponse(**new_parent, students=students_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create parent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create parent: {str(e)}"
        )

@router.get("/", response_model=List[ParentResponse])
async def get_parents(
    current_user: TokenPayload = Depends(require_admin)
):
    """Get all parents (Admin only)"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        parents = await db.select_all("parents", order_by="name")
        
        parents_response = []
        for parent in parents:
            # Get linked students
            students_data = supabase.table("parent_student").select(
                "students(*)"
            ).eq("parent_id", parent["parent_id"]).execute()
            
            students = []
            if students_data.data:
                for item in students_data.data:
                    if item.get("students"):
                        students.append(StudentResponse(**item["students"]))
            
            parents_response.append(ParentResponse(**parent, students=students))
        
        return parents_response
        
    except Exception as e:
        logger.error(f"Get parents error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve parents: {str(e)}"
        )

@router.get("/{parent_id}", response_model=ParentResponse)
async def get_parent(
    parent_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Get parent by ID"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        parent = await db.select_by_id("parents", "parent_id", parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent not found"
            )
        
        # Get linked students
        students_data = supabase.table("parent_student").select(
            "students(*)"
        ).eq("parent_id", parent_id).execute()
        
        students = []
        if students_data.data:
            for item in students_data.data:
                if item.get("students"):
                    students.append(StudentResponse(**item["students"]))
        
        return ParentResponse(**parent, students=students)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get parent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve parent: {str(e)}"
        )

@router.get("/{parent_id}/children")
async def get_parent_children(
    parent_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Get all children of a parent"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify parent exists
        parent = await db.select_by_id("parents", "parent_id", parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent not found"
            )
        
        # Get children with class information
        response = supabase.table("parent_student").select(
            "*, students(*, classes(class_name, section))"
        ).eq("parent_id", parent_id).execute()
        
        children = []
        for record in response.data:
            student = record.get("students")
            if student:
                class_info = None
                if student.get("classes"):
                    class_info = f"{student['classes']['class_name']} - {student['classes']['section']}"
                
                children.append({
                    "student_id": student["student_id"],
                    "name": student["name"],
                    "dob": student.get("dob"),
                    "email": student.get("email"),
                    "class": class_info,
                    "relationship": record.get("relationship")
                })
        
        return {
            "parent_id": parent_id,
            "parent_name": parent["name"],
            "children_count": len(children),
            "children": children
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get parent children error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve children: {str(e)}"
        )

@router.get("/{parent_id}/children/{student_id}/performance")
async def get_child_performance(
    parent_id: str,
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Get child's academic performance"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify parent-student relationship
        relationship = supabase.table("parent_student").select("*").eq(
            "parent_id", parent_id
        ).eq("student_id", student_id).execute()
        
        if not relationship.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this student's data"
            )
        
        # Get student info
        student = await db.select_by_id("students", "student_id", student_id)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Get attendance
        attendance = supabase.table("attendance").select("*").eq("student_id", student_id).execute()
        total_days = len(attendance.data)
        present_days = sum(1 for a in attendance.data if a["status"] == "present")
        attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
        
        # Get marks
        marks = supabase.table("marks").select(
            "*, exams(exam_name, max_marks, date, subjects(subject_name))"
        ).eq("student_id", student_id).execute()
        
        # Calculate average
        total_percentage = 0
        for mark in marks.data:
            exam = mark.get("exams")
            if exam and exam.get("max_marks"):
                percentage = (mark["marks_scored"] / exam["max_marks"]) * 100
                total_percentage += percentage
        
        avg_percentage = total_percentage / len(marks.data) if marks.data else 0
        
        return {
            "student_id": student_id,
            "student_name": student["name"],
            "attendance": {
                "total_days": total_days,
                "present_days": present_days,
                "percentage": round(attendance_percentage, 2)
            },
            "academic": {
                "total_exams": len(marks.data),
                "average_percentage": round(avg_percentage, 2),
                "recent_marks": marks.data[:5]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get child performance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve performance data: {str(e)}"
        )

@router.post("/{parent_id}/link-student/{student_id}")
async def link_student_to_parent(
    parent_id: str,
    student_id: str,
    relationship: str = "Guardian",
    current_user: TokenPayload = Depends(require_admin)
):
    """Link a student to a parent (Admin only)"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # Verify parent exists
        parent = await db.select_by_id("parents", "parent_id", parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent not found"
            )
        
        # Verify student exists
        student = await db.select_by_id("students", "student_id", student_id)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Check if relationship already exists
        existing = supabase.table("parent_student").select("*").eq(
            "parent_id", parent_id
        ).eq("student_id", student_id).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student is already linked to this parent"
            )
        
        # Create relationship
        await db.insert_one("parent_student", {
            "parent_id": parent_id,
            "student_id": student_id,
            "relationship": relationship
        })
        
        logger.info(f"Linked student {student_id} to parent {parent_id}")
        
        return {
            "message": "Student linked to parent successfully",
            "parent_id": parent_id,
            "student_id": student_id,
            "relationship": relationship
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Link student to parent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to link student to parent: {str(e)}"
        )

@router.delete("/{parent_id}/unlink-student/{student_id}")
async def unlink_student_from_parent(
    parent_id: str,
    student_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """Unlink a student from a parent (Admin only)"""
    supabase = get_supabase_client()
    
    try:
        # Check if relationship exists
        existing = supabase.table("parent_student").select("*").eq(
            "parent_id", parent_id
        ).eq("student_id", student_id).execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No relationship found between this parent and student"
            )
        
        # Delete relationship
        supabase.table("parent_student").delete().eq(
            "parent_id", parent_id
        ).eq("student_id", student_id).execute()
        
        logger.info(f"Unlinked student {student_id} from parent {parent_id}")
        
        return {
            "message": "Student unlinked from parent successfully",
            "parent_id": parent_id,
            "student_id": student_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unlink student from parent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unlink student from parent: {str(e)}"
        )

@router.delete("/{parent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parent(
    parent_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """Delete parent (Admin only)"""
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        parent = await db.select_by_id("parents", "parent_id", parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent not found"
            )
        
        # Delete parent (cascade will handle parent_student relationships)
        await db.delete_by_id("parents", "parent_id", parent_id)
        
        # Also delete user account if exists
        if parent.get("user_id"):
            try:
                await db.delete_by_id("users", "user_id", parent["user_id"])
            except:
                pass  # User might already be deleted
        
        logger.info(f"Parent deleted: {parent_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete parent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete parent: {str(e)}"
        )