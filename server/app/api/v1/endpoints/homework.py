"""
app/api/v1/endpoints/homework.py
Homework management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from datetime import date
from app.models.schemas import (
    HomeworkCreate, HomeworkUpdate, HomeworkResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user, require_teacher
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_homework_response(homework: dict, db: SupabaseQueries) -> dict:
    """Helper to add class_name, subject_name, and teacher_name."""
    
    class_name, subject_name, teacher_name = None, None, None
    
    if homework.get("class_id"):
        cls = await db.select_by_id("classes", "class_id", homework["class_id"])
        if cls:
            class_name = f"{cls.get('class_name', '')} - {cls.get('section', '')}"
            
    if homework.get("subject_id"):
        subject = await db.select_by_id("subjects", "subject_id", homework["subject_id"])
        if subject:
            subject_name = subject.get("subject_name")

    if homework.get("teacher_id"):
        teacher = await db.select_by_id("teachers", "teacher_id", homework["teacher_id"])
        if teacher:
            teacher_name = teacher.get("name")
            
    return {
        "class_name": class_name,
        "subject_name": subject_name,
        "teacher_name": teacher_name
    }


@router.post("/", response_model=HomeworkResponse, status_code=status.HTTP_201_CREATED)
async def create_homework(
    homework_data: HomeworkCreate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Create a new homework assignment.
    (Admin or Teacher only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify foreign keys
        if not await db.select_by_id("classes", "class_id", str(homework_data.class_id)):
            raise HTTPException(status_code=404, detail="Class not found")
        if not await db.select_by_id("subjects", "subject_id", str(homework_data.subject_id)):
            raise HTTPException(status_code=404, detail="Subject not found")
        
        # 2. Get Teacher ID from current user
        teacher = await db.select_one("teachers", {"user_id": current_user.sub})
        if not teacher and current_user.role != UserRole.ADMIN:
             raise HTTPException(status_code=404, detail="Teacher profile not found for this user.")
        
        # Admins can post on behalf of others, but teachers must use their own ID
        teacher_id_to_use = str(homework_data.teacher_id)
        if current_user.role == UserRole.TEACHER:
            teacher_id_to_use = teacher["teacher_id"]
        elif not await db.select_by_id("teachers", "teacher_id", teacher_id_to_use):
            raise HTTPException(status_code=404, detail="Teacher (teacher_id) not found.")

        # 3. Prepare data for insertion
        homework_dict = homework_data.model_dump()
        homework_dict["teacher_id"] = teacher_id_to_use
        
        # 4. Fix serialization for non-string types
        homework_dict["class_id"] = str(homework_dict["class_id"])
        homework_dict["subject_id"] = str(homework_dict["subject_id"])
        homework_dict["due_date"] = homework_dict["due_date"].isoformat()
        
        # 5. Insert new homework
        new_homework = await db.insert_one("homework", homework_dict)
        
        logger.info(f"Homework created: {new_homework['hw_id']}")
        
        # 6. Enrich and return response
        enriched_data = await _enrich_homework_response(new_homework, db)
        return HomeworkResponse(**new_homework, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create homework error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create homework: {str(e)}"
        )

@router.get("/", response_model=List[HomeworkResponse])
async def get_homework_list(
    class_id: Optional[str] = None,
    teacher_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of homework assignments.
    - Admins/Teachers see all or can filter.
    - Students see only their class's homework.
    - Parents see only their children's class homework.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    filters = {}
    class_ids_allowed = []

    try:
        # --- Role-based security ---
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student or not student.get("class_id"):
                return []
            class_ids_allowed = [student["class_id"]]
            filters["class_id"] = student["class_id"]
            
        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent: return []
            
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            child_student_ids = [link["student_id"] for link in links]
            if not child_student_ids: return []
            
            # Find all unique class IDs for their children
            children = await db.raw_query().table("students").select("class_id").in_("student_id", child_student_ids).execute()
            class_ids_allowed = list(set(c["class_id"] for c in children.data if c.get("class_id")))
            
            if not class_ids_allowed: return []
            
            # If parent is filtering for a specific class they have access to
            if class_id and class_id in class_ids_allowed:
                filters["class_id"] = class_id
            elif class_id: # Parent trying to access a class not their own
                 raise HTTPException(status_code=403, detail="Access denied")

        elif class_id: # Admin/Teacher filtering
            filters["class_id"] = class_id
            
        if teacher_id and current_user.role in [UserRole.ADMIN, UserRole.TEACHER]:
            filters["teacher_id"] = teacher_id
        # --- End security ---
        
        # Build query
        query = db.raw_query().table("homework").select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
            
        # Handle parent query for multiple classes
        if current_user.role == UserRole.PARENT and not class_id:
            query = query.in_("class_id", class_ids_allowed)
            
        response = query.order("due_date", desc=True).execute()
        homework_list = response.data
        
        # Enrich all entries
        response_list = []
        for hw in homework_list:
            enriched_data = await _enrich_homework_response(hw, db)
            response_list.append(HomeworkResponse(**hw, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get homework list error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve homework: {str(e)}"
        )

@router.get("/{hw_id}", response_model=HomeworkResponse)
async def get_homework(
    hw_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single homework assignment by its ID.
    - Students/Parents can only get homework for their class.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        hw = await db.select_by_id("homework", "hw_id", hw_id)
        if not hw:
            raise HTTPException(status_code=404, detail="Homework not found")

        # --- Authorization Check ---
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student or hw.get("class_id") != student.get("class_id"):
                raise HTTPException(status_code=403, detail="Access denied")
                
        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent:
                 raise HTTPException(status_code=403, detail="Access denied")
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            child_student_ids = [link["student_id"] for link in links]
            children = await db.raw_query().table("students").select("class_id").in_("student_id", child_student_ids).execute()
            class_ids_allowed = list(set(c["class_id"] for c in children.data if c.get("class_id")))
            
            if hw.get("class_id") not in class_ids_allowed:
                raise HTTPException(status_code=403, detail="Access denied")
        # --- End Auth Check ---

        enriched_data = await _enrich_homework_response(hw, db)
        return HomeworkResponse(**hw, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get homework error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve homework: {str(e)}"
        )

@router.put("/{hw_id}", response_model=HomeworkResponse)
async def update_homework(
    hw_id: str,
    homework_data: HomeworkUpdate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Update a homework assignment.
    (Admin or original author only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing homework
        existing = await db.select_by_id("homework", "hw_id", hw_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Homework not found")

        # 2. Authorization: Must be Admin or the author
        teacher = await db.select_one("teachers", {"user_id": current_user.sub})
        if current_user.role != UserRole.ADMIN:
            if not teacher or existing.get("teacher_id") != teacher["teacher_id"]:
                raise HTTPException(status_code=403, detail="Not authorized to update this homework")

        # 3. Prepare update data
        update_data = homework_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # 4. Serialize and validate foreign keys if they are changing
        for key in ["class_id", "subject_id", "teacher_id"]:
            if key in update_data:
                table_name = f"{key.split('_')[0]}s" # e.g., class_id -> classes
                if not await db.select_by_id(table_name, key, str(update_data[key])):
                    raise HTTPException(status_code=404, detail=f"{key.split('_')[0].capitalize()} not found")
                update_data[key] = str(update_data[key])
        
        if "due_date" in update_data:
            update_data["due_date"] = update_data["due_date"].isoformat()

        # 5. Update the homework
        updated_hw = await db.update_by_id("homework", "hw_id", hw_id, update_data)
        
        logger.info(f"Homework updated: {updated_hw['hw_id']}")

        # 6. Enrich and return response
        enriched_data = await _enrich_homework_response(updated_hw, db)
        return HomeworkResponse(**updated_hw, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update homework error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update homework: {str(e)}"
        )

@router.delete("/{hw_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_homework(
    hw_id: str,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Delete a homework assignment.
    (Admin or original author only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing homework
        existing = await db.select_by_id("homework", "hw_id", hw_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Homework not found")

        # 2. Authorization: Must be Admin or the author
        teacher = await db.select_one("teachers", {"user_id": current_user.sub})
        if current_user.role != UserRole.ADMIN:
            if not teacher or existing.get("teacher_id") != teacher["teacher_id"]:
                raise HTTPException(status_code=403, detail="Not authorized to delete this homework")
        
        # 3. Check for submissions (optional: prevent deletion if graded)
        submissions = await db.select_all("submissions", {"hw_id": hw_id})
        if submissions:
            logger.warning(f"Deleting homework {hw_id} which has {len(submissions)} submissions.")
            # You could add a rule here to prevent deletion if submissions exist
            # For now, we allow it but will also delete submissions.
            await db.delete_many("submissions", {"hw_id": hw_id})

        # 4. Delete homework
        await db.delete_by_id("homework", "hw_id", hw_id)
        
        logger.info(f"Homework deleted: {hw_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete homework error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete homework: {str(e)}"
        )