# """
# app/api/v1/endpoints/fees.py
# Fee management endpoints
# """
# from fastapi import APIRouter, HTTPException, status, Depends, Query
# from typing import List, Optional
# from datetime import date, datetime
# from app.models.schemas import (
#     FeeCreate, FeePayment, FeeResponse, FeeStatus,
#     TokenPayload, UserRole
# )
# from app.core.security import get_current_user, require_admin
# from app.db.supabase import get_supabase_client, SupabaseQueries
# from app.services.email_service import EmailService
# import logging

# logger = logging.getLogger(__name__)
# router = APIRouter()
# email_service = EmailService()

# @router.post("/", response_model=FeeResponse, status_code=status.HTTP_201_CREATED)
# async def create_fee(
#     fee_data: FeeCreate,
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """
#     Create fee record for a student (Admin only)
#     """
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         # Verify student exists
#         student = await db.select_by_id("students", "student_id", fee_data.student_id)
#         if not student:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Student not found"
#             )
        
#         # Create fee record
#         fee_dict = fee_data.model_dump()
#         fee_dict["date"] = str(fee_dict.get("due_date"))
#         fee_dict["balance"] = fee_dict["amount"]
        
#         new_fee = await db.insert_one("fees", fee_dict)
        
#         # Send email notification
#         if student.get("email"):
#             await email_service.send_email(
#                 to_email=student["email"],
#                 subject="New Fee Payment Due",
#                 html_content=f"""
#                 <h2>Fee Payment Notice</h2>
#                 <p>Dear {student['name']},</p>
#                 <p>A new fee has been added to your account:</p>
#                 <ul>
#                     <li>Type: {fee_data.fee_type}</li>
#                     <li>Amount: ₹{fee_data.amount}</li>
#                     <li>Due Date: {fee_data.due_date}</li>
#                 </ul>
#                 <p>Please make the payment before the due date.</p>
#                 """
#             )
        
#         logger.info(f"Fee created for student {fee_data.student_id}")
        
#         return FeeResponse(
#             **new_fee,
#             student_name=student["name"],
#             balance=new_fee["amount"]
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Create fee error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create fee record"
#         )

# @router.get("/", response_model=List[FeeResponse])
# async def get_fees(
#     student_id: Optional[str] = None,
#     status: Optional[FeeStatus] = None,
#     academic_year: Optional[str] = None,
#     page: int = Query(1, ge=1),
#     page_size: int = Query(20, ge=1, le=100),
#     current_user: TokenPayload = Depends(get_current_user)
# ):
#     """
#     Get fee records with filtering
#     """
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         filters = {}
        
#         # Role-based filtering
#         if current_user.role == UserRole.STUDENT:
#             # Students can only see their own fees
#             student_data = await db.select_all("students", {"user_id": current_user.sub})
#             if not student_data:
#                 return []
#             filters["student_id"] = student_data[0]["student_id"]
#         elif student_id:
#             filters["student_id"] = student_id
        
#         if status:
#             filters["status"] = status.value
        
#         if academic_year:
#             filters["academic_year"] = academic_year
        
#         # Get paginated fees
#         result = await db.paginate("fees", page, page_size, filters, "due_date")
        
#         # Enrich with student names
#         fees = []
#         for fee in result["data"]:
#             student = await db.select_by_id("students", "student_id", fee["student_id"])
#             student_name = student["name"] if student else None
            
#             balance = fee["amount"] - fee.get("amount_paid", 0)
            
#             fees.append(FeeResponse(
#                 **fee,
#                 student_name=student_name,
#                 balance=balance
#             ))
        
#         return fees
        
#     except Exception as e:
#         logger.error(f"Get fees error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to retrieve fee records"
#         )

# @router.post("/payment", response_model=FeeResponse)
# async def record_payment(
#     payment_data: FeePayment,
#     current_user: TokenPayload = Depends(get_current_user)
# ):
#     """
#     Record fee payment
#     Can be done by admin or the student/parent themselves
#     """
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         # Get fee record
#         fee = await db.select_by_id("fees", "fee_id", payment_data.fee_id)
#         if not fee:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Fee record not found"
#             )
        
#         # Authorization check
#         if current_user.role in [UserRole.STUDENT, UserRole.PARENT]:
#             student = await db.select_by_id("students", "student_id", fee["student_id"])
#             if current_user.role == UserRole.STUDENT:
#                 if student.get("user_id") != current_user.sub:
#                     raise HTTPException(
#                         status_code=status.HTTP_403_FORBIDDEN,
#                         detail="Access denied"
#                     )
        
#         # Calculate new amounts
#         current_paid = fee.get("amount_paid", 0)
#         new_paid = current_paid + payment_data.amount_paid
#         balance = fee["amount"] - new_paid
        
#         if new_paid > fee["amount"]:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Payment amount exceeds fee amount"
#             )
        
#         # Determine new status
#         if balance == 0:
#             new_status = FeeStatus.PAID.value
#         elif new_paid > 0:
#             new_status = FeeStatus.PARTIAL.value
#         else:
#             new_status = fee["status"]
        
#         # Update fee record
#         update_data = {
#             "amount_paid": new_paid,
#             "status": new_status,
#             "payment_date": datetime.now().isoformat(),
#             "payment_method": payment_data.payment_method,
#             "transaction_id": payment_data.transaction_id
#         }
        
#         updated_fee = await db.update_by_id(
#             "fees",
#             "fee_id",
#             payment_data.fee_id,
#             update_data
#         )
        
#         # Get student info for email
#         student = await db.select_by_id("students", "student_id", fee["student_id"])
        
#         # Send payment receipt email
#         if student and student.get("email"):
#             await email_service.send_email(
#                 to_email=student["email"],
#                 subject="Fee Payment Receipt",
#                 html_content=f"""
#                 <h2>Payment Receipt</h2>
#                 <p>Dear {student['name']},</p>
#                 <p>Your payment has been received successfully.</p>
#                 <h3>Payment Details:</h3>
#                 <ul>
#                     <li>Amount Paid: ₹{payment_data.amount_paid}</li>
#                     <li>Payment Method: {payment_data.payment_method}</li>
#                     <li>Transaction ID: {payment_data.transaction_id or 'N/A'}</li>
#                     <li>Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
#                 </ul>
#                 <h3>Fee Summary:</h3>
#                 <ul>
#                     <li>Total Fee: ₹{fee['amount']}</li>
#                     <li>Paid: ₹{new_paid}</li>
#                     <li>Balance: ₹{balance}</li>
#                     <li>Status: {new_status}</li>
#                 </ul>
#                 <p>Thank you for your payment!</p>
#                 """
#             )
        
#         logger.info(f"Payment recorded for fee {payment_data.fee_id}")
        
#         return FeeResponse(
#             **updated_fee,
#             student_name=student["name"] if student else None,
#             balance=balance
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Record payment error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to record payment"
#         )

# @router.get("/overdue")
# async def get_overdue_fees(
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """
#     Get list of overdue fees (Admin only)
#     """
#     supabase = get_supabase_client()
    
#     try:
#         today = date.today()
        
#         # Get overdue fees
#         response = supabase.table("fees").select(
#             "*, students(name, email, phone)"
#         ).lt("due_date", str(today)).neq("status", "paid").execute()
        
#         overdue_fees = []
#         total_overdue = 0
        
#         for fee in response.data:
#             balance = fee["amount"] - fee.get("amount_paid", 0)
#             total_overdue += balance
            
#             overdue_fees.append({
#                 "fee_id": fee["fee_id"],
#                 "student_id": fee["student_id"],
#                 "student_name": fee["students"]["name"],
#                 "student_email": fee["students"]["email"],
#                 "fee_type": fee["fee_type"],
#                 "amount": fee["amount"],
#                 "amount_paid": fee.get("amount_paid", 0),
#                 "balance": balance,
#                 "due_date": fee["due_date"],
#                 "days_overdue": (today - date.fromisoformat(fee["due_date"])).days
#             })
        
#         return {
#             "total_overdue_amount": total_overdue,
#             "total_overdue_count": len(overdue_fees),
#             "overdue_fees": sorted(overdue_fees, key=lambda x: x["days_overdue"], reverse=True)
#         }
        
#     except Exception as e:
#         logger.error(f"Get overdue fees error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to retrieve overdue fees"
#         )

# @router.post("/send-reminders")
# async def send_fee_reminders(
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """
#     Send email reminders for pending/overdue fees (Admin only)
#     """
#     supabase = get_supabase_client()
    
#     try:
#         # Get pending and overdue fees
#         response = supabase.table("fees").select(
#             "*, students(name, email)"
#         ).in_("status", ["pending", "overdue"]).execute()
        
#         sent_count = 0
        
#         for fee in response.data:
#             student = fee["students"]
#             if student and student.get("email"):
#                 balance = fee["amount"] - fee.get("amount_paid", 0)
                
#                 # Determine urgency
#                 due_date = date.fromisoformat(fee["due_date"])
#                 days_until_due = (due_date - date.today()).days
                
#                 if days_until_due < 0:
#                     urgency = f"OVERDUE by {abs(days_until_due)} days"
#                     subject = "⚠️ Fee Payment Overdue"
#                 elif days_until_due <= 3:
#                     urgency = f"Due in {days_until_due} days"
#                     subject = "🔔 Fee Payment Reminder - Urgent"
#                 else:
#                     urgency = f"Due in {days_until_due} days"
#                     subject = "🔔 Fee Payment Reminder"
                
#                 await email_service.send_email(
#                     to_email=student["email"],
#                     subject=subject,
#                     html_content=f"""
#                     <h2>Fee Payment Reminder</h2>
#                     <p>Dear {student['name']},</p>
#                     <p>This is a reminder about your pending fee payment:</p>
#                     <ul>
#                         <li>Fee Type: {fee['fee_type']}</li>
#                         <li>Amount: ₹{balance}</li>
#                         <li>Due Date: {fee['due_date']}</li>
#                         <li>Status: <strong>{urgency}</strong></li>
#                     </ul>
#                     <p>Please make the payment at your earliest convenience.</p>
#                     <p>For any queries, please contact the accounts department.</p>
#                     """
#                 )
#                 sent_count += 1
        
#         logger.info(f"Fee reminders sent to {sent_count} students")
        
#         return {
#             "message": f"Reminders sent successfully",
#             "emails_sent": sent_count
#         }
        
#     except Exception as e:
#         logger.error(f"Send fee reminders error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to send fee reminders"
#         )

# @router.get("/statistics")
# async def get_fee_statistics(
#     academic_year: Optional[str] = None,
#     current_user: TokenPayload = Depends(require_admin)
# ):
#     """
#     Get fee collection statistics (Admin only)
#     """
#     supabase = get_supabase_client()
    
#     try:
#         query = supabase.table("fees").select("*")
        
#         if academic_year:
#             query = query.eq("academic_year", academic_year)
        
#         response = query.execute()
#         fees = response.data
        
#         # Calculate statistics
#         total_expected = sum(f["amount"] for f in fees)
#         total_collected = sum(f.get("amount_paid", 0) for f in fees)
#         total_pending = total_expected - total_collected
        
#         paid_count = sum(1 for f in fees if f["status"] == "paid")
#         pending_count = sum(1 for f in fees if f["status"] == "pending")
#         overdue_count = sum(1 for f in fees if f["status"] == "overdue")
#         partial_count = sum(1 for f in fees if f["status"] == "partial")
        
#         collection_rate = (total_collected / total_expected * 100) if total_expected > 0 else 0
        
#         # Fee type breakdown
#         fee_types = {}
#         for fee in fees:
#             fee_type = fee["fee_type"]
#             if fee_type not in fee_types:
#                 fee_types[fee_type] = {
#                     "expected": 0,
#                     "collected": 0,
#                     "pending": 0
#                 }
#             fee_types[fee_type]["expected"] += fee["amount"]
#             fee_types[fee_type]["collected"] += fee.get("amount_paid", 0)
#             fee_types[fee_type]["pending"] += fee["amount"] - fee.get("amount_paid", 0)
        
#         return {
#             "summary": {
#                 "total_expected": total_expected,
#                 "total_collected": total_collected,
#                 "total_pending": total_pending,
#                 "collection_rate": round(collection_rate, 2)
#             },
#             "status_count": {
#                 "paid": paid_count,
#                 "pending": pending_count,
#                 "overdue": overdue_count,
#                 "partial": partial_count
#             },
#             "by_fee_type": fee_types,
#             "academic_year": academic_year or "All"
#         }
        
#     except Exception as e:
#         logger.error(f"Get fee statistics error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to retrieve fee statistics"
#         )

# @router.get("/{fee_id}", response_model=FeeResponse)
# async def get_fee(
#     fee_id: str,
#     current_user: TokenPayload = Depends(get_current_user)
# ):
#     """
#     Get fee details by ID
#     """
#     supabase = get_supabase_client()
#     db = SupabaseQueries(supabase)
    
#     try:
#         fee = await db.select_by_id("fees", "fee_id", fee_id)
        
#         if not fee:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Fee record not found"
#             )
        
#         # Authorization check
#         if current_user.role in [UserRole.STUDENT, UserRole.PARENT]:
#             student = await db.select_by_id("students", "student_id", fee["student_id"])
#             if current_user.role == UserRole.STUDENT:
#                 if student.get("user_id") != current_user.sub:
#                     raise HTTPException(
#                         status_code=status.HTTP_403_FORBIDDEN,
#                         detail="Access denied"
#                     )
        
#         # Get student name
#         student = await db.select_by_id("students", "student_id", fee["student_id"])
#         balance = fee["amount"] - fee.get("amount_paid", 0)
        
#         return FeeResponse(
#             **fee,
#             student_name=student["name"] if student else None,
#             balance=balance
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Get fee error: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to retrieve fee record"
#         )


"""
app/api/v1/endpoints/fees.py
Fee management endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import List, Optional
from datetime import date, datetime
from app.models.schemas import (
    FeeCreate, FeeUpdate, FeePayment, FeeResponse, FeeStatus,
    TokenPayload, UserRole
)
from app.core.security import get_current_user, require_admin
from app.db.supabase import get_supabase_client, SupabaseQueries
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _enrich_fee_response(fee: dict, db: SupabaseQueries) -> dict:
    """Helper to add student_name and calculate balance."""
    
    student_name = None
    if fee.get("student_id"):
        student = await db.select_by_id("students", "student_id", fee["student_id"])
        if student:
            student_name = student.get("name")
            
    # Calculate balance
    amount = fee.get("amount", 0)
    amount_paid = fee.get("amount_paid", 0)
    balance = amount - amount_paid
            
    return {
        "student_name": student_name,
        "balance": balance
    }


@router.post("/", response_model=FeeResponse, status_code=status.HTTP_201_CREATED)
async def create_fee(
    fee_data: FeeCreate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Create a fee record for a student (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Verify student exists
        if not await db.select_by_id("students", "student_id", str(fee_data.student_id)):
            raise HTTPException(status_code=404, detail="Student not found")
        
        # 2. Prepare data for insertion
        fee_dict = fee_data.model_dump()
        
        # 3. Fix serialization for non-string types
        fee_dict["student_id"] = str(fee_dict["student_id"])
        fee_dict["due_date"] = fee_dict["due_date"].isoformat()
        fee_dict["status"] = fee_dict["status"].value # Convert enum to string
        
        # 4. Insert new fee
        new_fee = await db.insert_one("fees", fee_dict)
        
        logger.info(f"Fee created for student {fee_data.student_id}")
        
        # 5. Enrich and return response
        enriched_data = await _enrich_fee_response(new_fee, db)
        return FeeResponse(**new_fee, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create fee error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create fee record: {str(e)}"
        )

@router.post("/payment", response_model=FeeResponse)
async def record_payment(
    payment_data: FeePayment,
    current_user: TokenPayload = Depends(get_current_user) # Allow Admin/Staff
):
    """
    Record a fee payment against an existing fee.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        # 1. Get existing fee record
        fee = await db.select_by_id("fees", "fee_id", str(payment_data.fee_id))
        if not fee:
            raise HTTPException(status_code=404, detail="Fee record not found")

        # 2. Check for overpayment
        current_paid = fee.get("amount_paid", 0)
        total_amount = fee.get("amount", 0)
        new_paid_amount = current_paid + payment_data.amount_paid
        
        if new_paid_amount > total_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Payment (₹{payment_data.amount_paid}) exceeds balance due (₹{total_amount - current_paid})"
            )

        # 3. Determine new status
        new_balance = total_amount - new_paid_amount
        new_status = FeeStatus.PARTIAL.value
        if new_balance == 0:
            new_status = FeeStatus.PAID.value
            
        # 4. Prepare update data
        update_data = {
            "amount_paid": new_paid_amount,
            "status": new_status,
            "payment_date": datetime.now().isoformat(),
            "payment_method": payment_data.payment_method,
            "transaction_id": payment_data.transaction_id
        }
        
        # 5. Update the fee record
        updated_fee = await db.update_by_id(
            "fees",
            "fee_id",
            str(payment_data.fee_id),
            update_data
        )
        
        logger.info(f"Payment recorded for fee {payment_data.fee_id}")
        
        # 6. Enrich and return response
        enriched_data = await _enrich_fee_response(updated_fee, db)
        return FeeResponse(**updated_fee, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Record payment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record payment: {str(e)}"
        )

@router.get("/", response_model=List[FeeResponse])
async def get_fees(
    student_id: Optional[str] = None,
    status: Optional[FeeStatus] = None,
    academic_year: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get fee records with filtering.
    - Students/Parents can only see their own.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    filters = {}
    student_ids_allowed = None

    # --- Role-based security ---
    if current_user.role == UserRole.STUDENT:
        student = await db.select_one("students", {"user_id": current_user.sub})
        if not student:
            return []
        student_ids_allowed = [student["student_id"]]
        filters["student_id"] = student["student_id"]
        
    elif current_user.role == UserRole.PARENT:
        parent = await db.select_one("parents", {"user_id": current_user.sub})
        if not parent:
            return []
        links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
        student_ids_allowed = [link["student_id"] for link in links]
        if not student_ids_allowed:
            return []
        # If parent is filtering for a *specific* child they own
        if student_id and student_id in student_ids_allowed:
            filters["student_id"] = student_id
        # If parent is *not* filtering, we'll fetch all and filter in Python
        elif student_id:
            raise HTTPException(status_code=403, detail="Access denied to this student's records")

    elif student_id: # Admin or Teacher filtering
        filters["student_id"] = student_id
    # --- End security ---
        
    if status:
        filters["status"] = status.value
    if academic_year:
        filters["academic_year"] = academic_year
        
    try:
        fees_list = await db.select_all("fees", filters, "due_date", ascending=False)
        
        response_list = []
        for fee in fees_list:
            # Post-fetch filter for Parent role
            if current_user.role == UserRole.PARENT and student_ids_allowed:
                if fee.get("student_id") not in student_ids_allowed:
                    continue

            enriched_data = await _enrich_fee_response(fee, db)
            response_list.append(FeeResponse(**fee, **enriched_data))
            
        return response_list
        
    except Exception as e:
        logger.error(f"Get fees error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve fee records: {str(e)}"
        )

@router.get("/{fee_id}", response_model=FeeResponse)
async def get_fee(
    fee_id: str,
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Get a single fee record by ID.
    - Students/Parents can only see their own.
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        fee = await db.select_by_id("fees", "fee_id", fee_id)
        if not fee:
            raise HTTPException(status_code=404, detail="Fee record not found")

        # --- Authorization Check ---
        if current_user.role == UserRole.STUDENT:
            student = await db.select_one("students", {"user_id": current_user.sub})
            if not student or fee.get("student_id") != student["student_id"]:
                raise HTTPException(status_code=403, detail="Access denied")
                
        elif current_user.role == UserRole.PARENT:
            parent = await db.select_one("parents", {"user_id": current_user.sub})
            if not parent:
                raise HTTPException(status_code=403, detail="Access denied")
            links = await db.select_all("parent_student", {"parent_id": parent["parent_id"]})
            student_ids_allowed = [link["student_id"] for link in links]
            if fee.get("student_id") not in student_ids_allowed:
                raise HTTPException(status_code=403, detail="Access denied")
        # --- End Auth Check ---

        enriched_data = await _enrich_fee_response(fee, db)
        return FeeResponse(**fee, **enriched_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get fee error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve fee record: {str(e)}"
        )

@router.put("/{fee_id}", response_model=FeeResponse)
async def update_fee(
    fee_id: str,
    fee_data: FeeUpdate,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Update a fee record's details (e.g., amount, due date).
    (Admin only)
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing_fee = await db.select_by_id("fees", "fee_id", fee_id)
        if not existing_fee:
            raise HTTPException(status_code=404, detail="Fee record not found")
        
        update_data = fee_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Re-check foreign keys if they are being changed
        if "student_id" in update_data:
            if not await db.select_by_id("students", "student_id", str(update_data["student_id"])):
                raise HTTPException(status_code=404, detail="Student not found")
            update_data["student_id"] = str(update_data["student_id"])

        # Serialize non-string types
        if "due_date" in update_data:
            update_data["due_date"] = update_data["due_date"].isoformat()
        if "status" in update_data:
            update_data["status"] = update_data["status"].value
            
        updated_fee = await db.update_by_id("fees", "fee_id", fee_id, update_data)
        
        logger.info(f"Fee updated: {fee_id}")
        
        enriched_data = await _enrich_fee_response(updated_fee, db)
        return FeeResponse(**updated_fee, **enriched_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update fee error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update fee: {str(e)}"
        )

@router.delete("/{fee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fee(
    fee_id: str,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Delete a fee record (Admin only).
    """
    supabase = get_supabase_client()
    db = SupabaseQueries(supabase)
    
    try:
        existing_fee = await db.select_by_id("fees", "fee_id", fee_id)
        if not existing_fee:
            raise HTTPException(status_code=404, detail="Fee record not found")
        
        # Rule: Don't delete a fee that has been partially or fully paid
        if existing_fee.get("amount_paid", 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete a fee record that has payments associated with it."
            )
            
        await db.delete_by_id("fees", "fee_id", fee_id)
        
        logger.info(f"Fee deleted: {fee_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete fee error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete fee: {str(e)}"
        )

@router.get("/statistics/summary", status_code=200)
async def get_fee_statistics(
    academic_year: Optional[str] = None,
    current_user: TokenPayload = Depends(require_admin)
):
    """
    Get fee collection statistics (Admin only)
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table("fees").select("*")
        
        if academic_year:
            query = query.eq("academic_year", academic_year)
        
        response = query.execute()
        fees = response.data
        
        if not fees:
            return {"summary": "No fee data found for the specified criteria."}

        total_expected = sum(f["amount"] for f in fees)
        total_collected = sum(f.get("amount_paid", 0) for f in fees)
        total_pending = total_expected - total_collected
        
        paid_count = sum(1 for f in fees if f["status"] == "paid")
        pending_count = sum(1 for f in fees if f["status"] == "pending")
        overdue_count = sum(1 for f in fees if f["status"] == "overdue")
        partial_count = sum(1 for f in fees if f["status"] == "partial")
        
        collection_rate = (total_collected / total_expected * 100) if total_expected > 0 else 0
        
        return {
            "summary": {
                "total_expected": total_expected,
                "total_collected": total_collected,
                "total_pending": total_pending,
                "collection_rate_percentage": round(collection_rate, 2)
            },
            "status_count": {
                "paid": paid_count,
                "pending": pending_count,
                "overdue": overdue_count,
                "partial": partial_count
            },
            "academic_year": academic_year or "All"
        }
        
    except Exception as e:
        logger.error(f"Get fee statistics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve fee statistics: {str(e)}"
        )