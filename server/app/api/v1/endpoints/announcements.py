"""
app/api/v1/endpoints/announcements.py
Announcement management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from datetime import datetime
from app.models.schemas import (
    AnnouncementCreate, AnnouncementUpdate, AnnouncementResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user, require_teacher
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_announcement_response(announcement: dict, db: SupabaseQueries) -> dict:
    """Helper to add teacher_name."""
    
    teacher_name = None
    if announcement.get("teacher_id"):
        teacher = await db.select_by_id("teachers", "teacher_id", announcement["teacher_id"])
        if teacher:
            teacher_name = teacher.get("name")
            
    return {"teacher_name": teacher_name}


@router.post("/", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    announcement_data: AnnouncementCreate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Post a new announcement.
    (Admin or Teacher only)
    
    Note: The `teacher_id` in the payload MUST match an existing teacher.
    In a future version, this should be derived from the logged-in user.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify foreign keys
        if not await db.select_by_id("teachers", "teacher_id", str(announcement_data.teacher_id)):
            raise HTTPException(status_code=404, detail="Teacher not found")
            
        if announcement_data.class_id and not await db.select_by_id("classes", "class_id", str(announcement_data.class_id)):
            raise HTTPException(status_code=404, detail="Class not found")

        # 2. Prepare data for insertion
        announcement_dict = announcement_data.model_dump()
        
        # 3. Fix serialization for non-string types
        announcement_dict["teacher_id"] = str(announcement_dict["teacher_id"])
        if announcement_dict.get("class_id"):
            announcement_dict["class_id"] = str(announcement_dict["class_id"])
            
        # 4. Set the post date
        announcement_dict["date"] = datetime.now().isoformat()
        
        # 5. Insert new announcement
        new_announcement = await db.insert_one("announcements", announcement_dict)
        
        logger.info(f"Announcement created: {new_announcement['announcement_id']}")
        
        # 6. Enrich and return response
        enriched_data = await _enrich_announcement_response(new_announcement, db)
        return AnnouncementResponse(**new_announcement, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create announcement error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create announcement: {str(e)}"
        )

@router.get("/", response_model=List[AnnouncementResponse])
async def get_announcements(
    class_id: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of announcements.
    - Filters based on user role (Student, Parent).
    - Admins/Teachers see all.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        query = supabase.table("announcements").select("*")

        # Role-based filtering
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            targets = ["all", "students"]
            query = query.in_("target_audience", targets)
            # Filter for their class OR class-agnostic
            if student and student.get("class_id"):
                query = query.or_(f"class_id.eq.{student['class_id']},class_id.is.null")
        
        elif current_user.role == UserRole.PARENT:
            targets = ["all", "parents"]
            query = query.in_("target_audience", targets)
            # You could add logic here to also get announcements for their children's classes
        
        # Admin/Teacher can filter by class
        if class_id and current_user.role in [UserRole.ADMIN, UserRole.TEACHER]:
            query = query.eq("class_id", class_id)
            
        query = query.order("date", desc=True)
        response = query.execute()
        
        announcements = response.data
        
        # Enrich all announcements
        response_list = []
        for ann in announcements:
            enriched_data = await _enrich_announcement_response(ann, db)
            response_list.append(AnnouncementResponse(**ann, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get announcements error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve announcements: {str(e)}"
        )

@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(
    announcement_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single announcement by its ID.
    (Accessible to all logged-in users)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        announcement = await db.select_by_id("announcements", "announcement_id", announcement_id)
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Note: You could add role-based auth here if announcements are sensitive
        
        enriched_data = await _enrich_announcement_response(announcement, db)
        return AnnouncementResponse(**announcement, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get announcement error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve announcement: {str(e)}"
        )

@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: str,
    announcement_data: AnnouncementUpdate,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Update an announcement.
    (Admin or original author only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing announcement
        existing = await db.select_by_id("announcements", "announcement_id", announcement_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")

        # 2. Authorization: Must be Admin or the author
        teacher = await db.select_one("teachers", {"user_id": current_user.sub})
        if current_user.role != UserRole.ADMIN:
            if not teacher or existing.get("teacher_id") != teacher["teacher_id"]:
                raise HTTPException(status_code=403, detail="Not authorized to update this announcement")

        # 3. Prepare update data
        update_data = announcement_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # 4. Check foreign key if class_id is changing
        if "class_id" in update_data and update_data["class_id"]:
            if not await db.select_by_id("classes", "class_id", str(update_data["class_id"])):
                raise HTTPException(status_code=404, detail="Class not found")
            update_data["class_id"] = str(update_data["class_id"])

        # 5. Update the announcement
        updated_ann = await db.update_by_id("announcements", "announcement_id", announcement_id, update_data)
        
        logger.info(f"Announcement updated: {updated_ann['announcement_id']}")

        # 6. Enrich and return response
        enriched_data = await _enrich_announcement_response(updated_chn, db)
        return AnnouncementResponse(**updated_ann, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update announcement error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update announcement: {str(e)}"
        )

@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    announcement_id: str,
    current_user: TokenPayload = Depends(require_teacher) # Teachers or Admins
):
    """
    Delete an announcement.
    (Admin or original author only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing announcement
        existing = await db.select_by_id("announcements", "announcement_id", announcement_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")

        # 2. Authorization: Must be Admin or the author
        teacher = await db.select_one("teachers", {"user_id": current_user.sub})
        if current_user.role != UserRole.ADMIN:
            if not teacher or existing.get("teacher_id") != teacher["teacher_id"]:
                raise HTTPException(status_code=403, detail="Not authorized to delete this announcement")
            
        # 3. Delete
        await db.delete_by_id("announcements", "announcement_id", announcement_id)
        
        logger.info(f"Announcement deleted: {announcement_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete announcement error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete announcement: {str(e)}"
        )