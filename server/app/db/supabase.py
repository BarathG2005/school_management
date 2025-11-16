"""
app/db/supabase.py
Complete Supabase client configuration and helper functions
"""
from supabase import create_client, Client
from app.core.config import settings
from functools import lru_cache
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# ============================================
# CLIENT FACTORY FUNCTIONS
# ============================================

@lru_cache()
def get_supabase_client() -> Client:
    """
    Get Supabase client instance (cached)
    Uses the anon/public key - for regular operations
    
    Returns:
        Client: Supabase client instance
        
    Raises:
        Exception: If client creation fails
    """
    try:
        supabase: Client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_KEY
        )
        logger.info("Supabase client created successfully")
        return supabase
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        raise Exception(f"Supabase connection failed: {str(e)}")


@lru_cache()
def get_supabase_admin_client() -> Client:
    """
    Get Supabase admin client with service role key
    Use this for admin operations that bypass Row Level Security
    
    Returns:
        Client: Supabase admin client instance
        
    Raises:
        Exception: If admin client creation fails
    """
    try:
        supabase: Client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_KEY
        )
        logger.info("Supabase admin client created successfully")
        return supabase
    except Exception as e:
        logger.error(f"Failed to create Supabase admin client: {e}")
        raise Exception(f"Supabase admin connection failed: {str(e)}")


# ============================================
# HELPER CLASS FOR COMMON QUERIES
# ============================================

class SupabaseQueries:
    """
    Helper class for common Supabase database operations
    Provides simplified methods for CRUD operations
    """
    
    def __init__(self, client: Client = None):
        """
        Initialize SupabaseQueries
        
        Args:
            client: Optional Supabase client. If not provided, creates a new one.
        """
        self.client = client or get_supabase_client()
    
    # ============================================
    # CREATE OPERATIONS
    # ============================================
    
    async def insert_one(self, table: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.table(table).insert(data).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Inserted record into {table}")
                return response.data[0]
            else:
                logger.warning(f"Insert into {table} returned no data")
                return None
                
        except Exception as e:
            logger.error(f"Error inserting into {table}: {e}")
            raise Exception(f"Failed to insert into {table}: {str(e)}")
    
    async def insert_many(self, table: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Insert multiple records into a table
        
        Args:
            table: Table name
            data: List of dictionaries containing the data to insert
            
        Returns:
            list: List of inserted records
            
        Raises:
            Exception: If bulk insert operation fails
            
        Example:
            >>> students = await db.insert_many("students", [
            ...     {"name": "John", "dob": "2010-05-15"},
            ...     {"name": "Jane", "dob": "2010-06-20"}
            ... ])
        """
        try:
            response = self.client.table(table).insert(data).execute()
            logger.info(f"Bulk inserted {len(response.data)} records into {table}")
            return response.data
            
        except Exception as e:
            logger.error(f"Error bulk inserting into {table}: {e}")
            raise Exception(f"Failed to bulk insert into {table}: {str(e)}")
    
    # ============================================
    # READ OPERATIONS
    # ============================================
    
    async def select_all(
        self, 
        table: str, 
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        ascending: bool = True,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Select all records from a table with optional filters
        
        Args:
            table: Table name
            filters: Dictionary of column:value pairs to filter by
            order_by: Column name to order results by
            ascending: Sort direction (True for ASC, False for DESC)
            limit: Maximum number of records to return
            
        Returns:
            list: List of records matching the criteria
            
        Example:
            >>> # Get all students in a specific class
            >>> students = await db.select_all(
            ...     "students", 
            ...     filters={"class_id": "some-uuid"},
            ...     order_by="name"
            ... )
        """
        try:
            query = self.client.table(table).select("*")
            
            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            # Apply ordering
            if order_by:
                query = query.order(order_by, desc=not ascending)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            logger.info(f"Selected {len(response.data)} records from {table}")
            return response.data
            
        except Exception as e:
            logger.error(f"Error selecting from {table}: {e}")
            raise Exception(f"Failed to select from {table}: {str(e)}")
    
    async def select_by_id(
        self, 
        table: str, 
        id_column: str, 
        id_value: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Select a single record by its ID
        
        Args:
            table: Table name
            id_column: Name of the ID column (e.g., "student_id")
            id_value: Value of the ID to search for
            
        Returns:
            dict: The record if found, None otherwise
            
        Example:
            >>> student = await db.select_by_id(
            ...     "students", 
            ...     "student_id", 
            ...     "uuid-here"
            ... )
        """
        try:
            response = self.client.table(table).select("*").eq(id_column, id_value).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Found record in {table} with {id_column}={id_value}")
                return response.data[0]
            else:
                logger.info(f"No record found in {table} with {id_column}={id_value}")
                return None
                
        except Exception as e:
            logger.error(f"Error selecting from {table} by ID: {e}")
            raise Exception(f"Failed to select from {table}: {str(e)}")
    
    async def select_one(
        self, 
        table: str, 
        filters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Select a single record matching the filters
        
        Args:
            table: Table name
            filters: Dictionary of column:value pairs to filter by
            
        Returns:
            dict: The first matching record, None if no match
            
        Example:
            >>> user = await db.select_one(
            ...     "users", 
            ...     {"email": "john@example.com"}
            ... )
        """
        try:
            query = self.client.table(table).select("*")
            
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.limit(1).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error selecting one from {table}: {e}")
            raise Exception(f"Failed to select from {table}: {str(e)}")
    
    # ============================================
    # UPDATE OPERATIONS
    # ============================================
    
    async def update_by_id(
        self, 
        table: str, 
        id_column: str, 
        id_value: Any, 
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a record by its ID
        
        Args:
            table: Table name
            id_column: Name of the ID column
            id_value: Value of the ID
            data: Dictionary of fields to update
            
        Returns:
            dict: Updated record
            
        Example:
            >>> updated = await db.update_by_id(
            ...     "students",
            ...     "student_id",
            ...     "uuid-here",
            ...     {"name": "Updated Name", "phone": "1234567890"}
            ... )
        """
        try:
            response = self.client.table(table).update(data).eq(id_column, id_value).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Updated record in {table} with {id_column}={id_value}")
                return response.data[0]
            else:
                logger.warning(f"Update in {table} returned no data")
                return None
                
        except Exception as e:
            logger.error(f"Error updating {table}: {e}")
            raise Exception(f"Failed to update {table}: {str(e)}")
    
    async def update_many(
        self, 
        table: str, 
        filters: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Update multiple records matching filters
        
        Args:
            table: Table name
            filters: Dictionary of column:value pairs to filter records
            data: Dictionary of fields to update
            
        Returns:
            list: List of updated records
            
        Example:
            >>> # Update all students in a class
            >>> updated = await db.update_many(
            ...     "students",
            ...     {"class_id": "uuid"},
            ...     {"status": "active"}
            ... )
        """
        try:
            query = self.client.table(table).update(data)
            
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.execute()
            logger.info(f"Updated {len(response.data)} records in {table}")
            return response.data
            
        except Exception as e:
            logger.error(f"Error updating multiple records in {table}: {e}")
            raise Exception(f"Failed to update {table}: {str(e)}")
    
    # ============================================
    # DELETE OPERATIONS
    # ============================================
    
    async def delete_by_id(
        self, 
        table: str, 
        id_column: str, 
        id_value: Any
    ) -> List[Dict[str, Any]]:
        """
        Delete a record by its ID
        
        Args:
            table: Table name
            id_column: Name of the ID column
            id_value: Value of the ID
            
        Returns:
            list: Deleted record(s)
            
        Example:
            >>> deleted = await db.delete_by_id(
            ...     "students",
            ...     "student_id",
            ...     "uuid-here"
            ... )
        """
        try:
            response = self.client.table(table).delete().eq(id_column, id_value).execute()
            logger.info(f"Deleted record from {table} with {id_column}={id_value}")
            return response.data
            
        except Exception as e:
            logger.error(f"Error deleting from {table}: {e}")
            raise Exception(f"Failed to delete from {table}: {str(e)}")
    
    async def delete_many(
        self, 
        table: str, 
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Delete multiple records matching filters
        
        Args:
            table: Table name
            filters: Dictionary of column:value pairs to filter records
            
        Returns:
            list: List of deleted records
            
        Example:
            >>> # Delete all pending leave requests
            >>> deleted = await db.delete_many(
            ...     "leave_requests",
            ...     {"status": "pending"}
            ... )
        """
        try:
            query = self.client.table(table).delete()
            
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.execute()
            logger.info(f"Deleted {len(response.data)} records from {table}")
            return response.data
            
        except Exception as e:
            logger.error(f"Error deleting multiple from {table}: {e}")
            raise Exception(f"Failed to delete from {table}: {str(e)}")
    
    # ============================================
    # PAGINATION
    # ============================================
    
    async def paginate(
        self, 
        table: str, 
        page: int = 1,
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        ascending: bool = True
    ) -> Dict[str, Any]:
        """
        Paginate records from a table
        
        Args:
            table: Table name
            page: Page number (1-indexed)
            page_size: Number of records per page
            filters: Optional filters to apply
            order_by: Column to order by
            ascending: Sort direction
            
        Returns:
            dict: Contains 'data', 'count', 'page', 'page_size', 'total_pages'
            
        Example:
            >>> result = await db.paginate(
            ...     "students",
            ...     page=1,
            ...     page_size=20,
            ...     filters={"class_id": "uuid"},
            ...     order_by="name"
            ... )
            >>> print(f"Total: {result['count']}, Page: {result['page']}")
            >>> for student in result['data']:
            ...     print(student['name'])
        """
        try:
            # Calculate range for pagination
            start = (page - 1) * page_size
            end = start + page_size - 1
            
            # Build query with count
            query = self.client.table(table).select("*", count="exact")
            
            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            # Apply ordering
            if order_by:
                query = query.order(order_by, desc=not ascending)
            
            # Apply pagination range
            response = query.range(start, end).execute()
            
            # Calculate total pages
            total_count = response.count if response.count else 0
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
            
            logger.info(f"Paginated {table}: page {page}/{total_pages}, {len(response.data)} records")
            
            return {
                "data": response.data,
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
            
        except Exception as e:
            logger.error(f"Error paginating {table}: {e}")
            raise Exception(f"Failed to paginate {table}: {str(e)}")
    
    # ============================================
    # ADVANCED QUERIES
    # ============================================
    
    async def count(
        self, 
        table: str, 
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count records in a table
        
        Args:
            table: Table name
            filters: Optional filters to apply
            
        Returns:
            int: Number of records
            
        Example:
            >>> total_students = await db.count("students")
            >>> active_students = await db.count(
            ...     "students", 
            ...     {"is_active": True}
            ... )
        """
        try:
            query = self.client.table(table).select("*", count="exact")
            
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            response = query.limit(0).execute()
            count = response.count if response.count else 0
            
            logger.info(f"Counted {count} records in {table}")
            return count
            
        except Exception as e:
            logger.error(f"Error counting {table}: {e}")
            raise Exception(f"Failed to count {table}: {str(e)}")
    
    async def exists(
        self, 
        table: str, 
        filters: Dict[str, Any]
    ) -> bool:
        """
        Check if a record exists
        
        Args:
            table: Table name
            filters: Dictionary of column:value pairs to check
            
        Returns:
            bool: True if record exists, False otherwise
            
        Example:
            >>> email_exists = await db.exists(
            ...     "users",
            ...     {"email": "john@example.com"}
            ... )
        """
        try:
            query = self.client.table(table).select("*")
            
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.limit(1).execute()
            exists = len(response.data) > 0
            
            logger.info(f"Record {'exists' if exists else 'does not exist'} in {table}")
            return exists
            
        except Exception as e:
            logger.error(f"Error checking existence in {table}: {e}")
            raise Exception(f"Failed to check existence in {table}: {str(e)}")
    
    # ============================================
    # CUSTOM QUERIES
    # ============================================
    
    def raw_query(self):
        """
        Get the raw Supabase client for custom queries
        
        Returns:
            Client: Raw Supabase client
            
        Example:
            >>> db = SupabaseQueries()
            >>> # Complex custom query
            >>> response = db.raw_query().table("students").select(
            ...     "*, classes(class_name), marks(marks_scored)"
            ... ).eq("class_id", "uuid").execute()
        """
        return self.client


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

async def test_connection() -> bool:
    """
    Test Supabase connection
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        client = get_supabase_client()
        # Try a simple query
        response = client.table("users").select("user_id").limit(1).execute()
        logger.info("✓ Supabase connection test successful")
        return True
    except Exception as e:
        logger.error(f"✗ Supabase connection test failed: {e}")
        return False


async def initialize_database():
    """
    Initialize database connection and verify tables exist
    Run this on application startup
    """
    try:
        logger.info("Initializing database connection...")
        
        # Test connection
        if not await test_connection():
            raise Exception("Database connection test failed")
        
        # Verify critical tables exist
        db = SupabaseQueries()
        critical_tables = ["users", "students", "teachers", "classes"]
        
        for table in critical_tables:
            try:
                await db.count(table)
                logger.info(f"✓ Table '{table}' verified")
            except Exception as e:
                logger.error(f"✗ Table '{table}' not found or inaccessible: {e}")
                raise Exception(f"Critical table '{table}' is missing")
        
        logger.info("✓ Database initialization complete")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


# ============================================
# EXPORT
# ============================================

__all__ = [
    'get_supabase_client',
    'get_supabase_admin_client',
    'SupabaseQueries',
    'test_connection',
    'initialize_database'
]