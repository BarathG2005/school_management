# """
# app/api/v1/endpoints/timetable.py
# Timetable management endpoints
# """
# from fastapi import APIRouter, HTTPException, status, Depends
# from app.models.schemas import TimetableCreate, TimetableResponse, TokenPayload
# from app.core.security import require_admin, get_current_user
# from app.db.supabase import get_supabase_client, SupabaseQueries
# import logging

# logger = logging.getLogger(__name__)
# timetable_router = APIRouter()

# @timetable_router.post("/", response_model=TimetableResponse, status_code=status.HTTP_201_CREATED)
# async def create_timetable_entry(
#     timetable_data: TimetableCreate,
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """Create timetable entry (Admin only)"""
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         # Check for conflicts
#         existing = supabase.table("timetable").select("*").eq(
#             "class_id", timetable_data.class_id
#         ).eq("day", timetable_data.day).eq(
#             "period_number", timetable_data.period_number
#         ).execute()
        
#         if existing.data:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Timetable entry already exists for this period"
#             )
        
#         # Check teacher availability
#         teacher_conflict = supabase.table("timetable").select("*").eq(
#             "teacher_id", timetable_data.teacher_id
#         ).eq("day", timetable_data.day).eq(
#             "period_number", timetable_data.period_number
#         ).execute()
        
#         if teacher_conflict.data:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Teacher is already assigned to another class in this period"
#             )
        
#         timetable_dict = timetable_data.model_dump()
#         new_entry = await db.insert_one("timetable", timetable_dict)
        
#         # Get related data
#         cls = await db.select_by_id("classes", "class_id", timetable_data.class_id)
#         subject = await db.select_by_id("subjects", "subject_id", timetable_data.subject_id)
#         teacher = await db.select_by_id("teachers", "teacher_id", timetable_data.teacher_id)
        
#         return TimetableResponse(
#             **new_entry,
#             class_name=f"{cls['class_name']} - {cls['section']}" if cls else None,
#             subject_name=subject["subject_name"] if subject else None,
#             teacher_name=teacher["name"] if teacher else None
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Create timetable error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create timetable entry"
#         )

# @timetable_router.delete("/{timetable_id}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_timetable_entry(
#     timetable_id: str,
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """Delete timetable entry (Admin only)"""
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         existing = await db.select_by_id("timetable", "timetable_id", timetable_id)
#         if not existing:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Timetable entry not found"
#             )
        
#         await db.delete_by_id("timetable", "timetable_id", timetable_id)
#         logger.info(f"Timetable entry deleted: {timetable_id}")
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Delete timetable error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to delete timetable entry"
#         )



"""
app/api/v1/endpoints/timetable.py
Timetable management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from app.models.schemas import (
    TimetableCreate, TimetableUpdate, TimetableResponse, TokenPayload, UserRole
)
from app.core.security import require_admin, get_current_user
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_timetable_response(entry: dict, db: SupabaseQueries) -> dict:
    """Helper to add class_name, subject_name, and teacher_name."""
    
    class_name, subject_name, teacher_name = None, None, None
    
    if entry.get("class_id"):
        cls = await db.select_by_id("classes", "class_id", entry["class_id"])
        if cls:
            class_name = f"{cls.get('class_name', '')} - {cls.get('section', '')}"
            
    if entry.get("subject_id"):
        subject = await db.select_by_id("subjects", "subject_id", entry["subject_id"])
        if subject:
            subject_name = subject.get("subject_name")

    if entry.get("teacher_id"):
        teacher = await db.select_by_id("teachers", "teacher_id", entry["teacher_id"])
        if teacher:
            teacher_name = teacher.get("name")
            
    return {
        "class_name": class_name,
        "subject_name": subject_name,
        "teacher_name": teacher_name
    }


@router.post("/", response_model=TimetableResponse, status_code=status.HTTP_201_CREATED)
async def create_timetable_entry(
    entry_data: TimetableCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a new timetable entry (Admin only).
    Checks for conflicts for both the class and the teacher.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify foreign keys
        if not await db.select_by_id("classes", "class_id", str(entry_data.class_id)):
            raise HTTPException(status_code=404, detail="Class not found")
        if not await db.select_by_id("subjects", "subject_id", str(entry_data.subject_id)):
            raise HTTPException(status_code=404, detail="Subject not found")
        if not await db.select_by_id("teachers", "teacher_id", str(entry_data.teacher_id)):
            raise HTTPException(status_code=404, detail="Teacher not found")

        # 2. Check for Class conflict (Class, Day, Period)
        class_conflict = await db.select_one("timetable", {
            "class_id": str(entry_data.class_id),
            "day": entry_data.day,
            "period_number": entry_data.period_number
        })
        if class_conflict:
            raise HTTPException(status_code=409, detail="This class already has a period at this time.")

        # 3. Check for Teacher conflict (Teacher, Day, Period)
        teacher_conflict = await db.select_one("timetable", {
            "teacher_id": str(entry_data.teacher_id),
            "day": entry_data.day,
            "period_number": entry_data.period_number
        })
        if teacher_conflict:
            raise HTTPException(status_code=409, detail="This teacher is already assigned to another class at this time.")

        # 4. Prepare data for insertion
        entry_dict = entry_data.model_dump()
        entry_dict["class_id"] = str(entry_dict["class_id"])
        entry_dict["subject_id"] = str(entry_dict["subject_id"])
        entry_dict["teacher_id"] = str(entry_dict["teacher_id"])
        
        # 5. Insert new entry
        new_entry = await db.insert_one("timetable", entry_dict)
        
        logger.info(f"Timetable entry created: {new_entry['timetable_id']}")
        
        # 6. Enrich and return response
        enriched_data = await _enrich_timetable_response(new_entry, db)
        return TimetableResponse(**new_entry, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create timetable entry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create entry: {str(e)}"
        )

@router.get("/", response_model=List[TimetableResponse])
async def get_timetable_entries(
    class_id: Optional[str] = None,
    teacher_id: Optional[str] = None,
    day: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a list of all timetable entries, with optional filters.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        filters = {}
        if class_id:
            filters["class_id"] = class_id
        if teacher_id:
            filters["teacher_id"] = teacher_id
        if day:
            filters["day"] = day
        
        entries = await db.select_all("timetable", filters=filters, order_by="period_number")
        
        # Enrich all entries
        response_list = []
        for entry in entries:
            enriched_data = await _enrich_timetable_response(entry, db)
            response_list.append(TimetableResponse(**entry, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get timetable entries error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve timetable: {str(e)}"
        )

@router.get("/{timetable_id}", response_model=TimetableResponse)
async def get_timetable_entry(
    timetable_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single timetable entry by its ID
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        entry = await db.select_by_id("timetable", "timetable_id", timetable_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Timetable entry not found")
        
        enriched_data = await _enrich_timetable_response(entry, db)
        return TimetableResponse(**entry, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get timetable entry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve entry: {str(e)}"
        )

@router.put("/{timetable_id}", response_model=TimetableResponse)
async def update_timetable_entry(
    timetable_id: str,
    entry_data: TimetableUpdate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update a timetable entry (Admin only).
    Checks for conflicts on update.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing entry
        existing_entry = await db.select_by_id("timetable", "timetable_id", timetable_id)
        if not existing_entry:
            raise HTTPException(status_code=404, detail="Timetable entry not found")

        update_data = entry_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # 2. Merge existing data with update data for validation
        merged_data = existing_entry.copy()
        merged_data.update(update_data)
        
        # 3. Serialize UUIDs for validation and update
        for key in ["class_id", "subject_id", "teacher_id"]:
            if key in update_data:
                # Verify foreign key exists if it's being changed
                table_name = f"{key.split('_')[0]}s" # class_id -> classes
                if not await db.select_by_id(table_name, key, str(update_data[key])):
                     raise HTTPException(status_code=404, detail=f"{key.split('_')[0].capitalize()} not found")
                # Convert to string for DB
                update_data[key] = str(update_data[key])
                merged_data[key] = str(update_data[key]) # ensure merged data is also string
        
        # 4. Check for Class conflict
        class_conflict = await db.select_one("timetable", {
            "class_id": merged_data["class_id"],
            "day": merged_data["day"],
            "period_number": merged_data["period_number"]
        })
        if class_conflict and class_conflict["timetable_id"] != timetable_id:
            raise HTTPException(status_code=409, detail="This class already has a period at this time.")

        # 5. Check for Teacher conflict
        teacher_conflict = await db.select_one("timetable", {
            "teacher_id": merged_data["teacher_id"],
            "day": merged_data["day"],
            "period_number": merged_data["period_number"]
        })
        if teacher_conflict and teacher_conflict["timetable_id"] != timetable_id:
            raise HTTPException(status_code=409, detail="This teacher is already assigned at this time.")

        # 6. Update the entry
        updated_entry = await db.update_by_id("timetable", "timetable_id", timetable_id, update_data)
        
        logger.info(f"Timetable entry updated: {updated_entry['timetable_id']}")

        # 7. Enrich and return response
        enriched_data = await _enrich_timetable_response(updated_entry, db)
        return TimetableResponse(**updated_entry, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update timetable entry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update entry: {str(e)}"
        )

@router.delete("/{timetable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timetable_entry(
    timetable_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete a timetable entry (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        if not await db.select_by_id("timetable", "timetable_id", timetable_id):
            raise HTTPException(status_code=404, detail="Timetable entry not found")
            
        await db.delete_by_id("timetable", "timetable_id", timetable_id)
        
        logger.info(f"Timetable entry deleted: {timetable_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete timetable entry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete entry: {str(e)}"
        )