# Services Folder Implementation Rules (`app/services/`)

<directory_architecture>
**Domain Organization**:
- Create one folder per business domain: `user/`, `agent/`
- Each domain folder MUST contain `__init__.py`
- Domain folders should align with route modules and business capabilities

**Required Files Per Domain**:
```
app/services/user/
├── __init__.py
├── user_service.py      # Business logic and orchestration
└── user_repository.py   # Database operations and queries
```

**Domain Boundaries**: Each domain is self-contained and communicates with other domains only through service interfaces, never directly accessing other domains' repositories.
</directory_architecture>

<service_layer_specification>
**Business Logic Responsibilities**:
- Input validation and business rule enforcement
- Complex calculations and data transformations
- Cross-domain coordination and orchestration
- External API integration and third-party service calls
- Event publishing and domain event handling

**Strict Prohibitions**:
- NO direct database queries or ORM operations
- NO SQL statements or database connection handling
- NO HTTP status codes, request/response objects, or web framework imports
- NO direct file system operations (delegate to utility layer)

**Service Function Template**:
```python
async def create_user(user_data: CreateUserRequest) -> ServiceResult[User]:
    """Create a new user with business validation."""
    # 1. Business validation
    # 2. Call repository operations
    # 3. Handle domain events
    # 4. Return structured result
```
</service_layer_specification>

<repository_layer_specification>
**Database Operation Responsibilities**:
- All SQLModel/SQLAlchemy database operations
- Query construction and optimization
- Transaction management and rollback handling
- Database constraint validation
- Data persistence and retrieval

**Repository Function Template**:
```python
async def create_user(user: User) -> User:
    """Persist user to database."""
    async with get_db_session() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
```

**Query Patterns**:
- Use SQLModel select() statements for type safety
- Implement pagination using limit/offset parameters
- Include soft delete filtering by default
- Use database transactions for multi-step operations
</repository_layer_specification>

<dependency_hierarchy>
**Allowed Dependencies**:
- Services MAY depend on repositories within the same domain
- Services MAY depend on other services (with careful circular dependency prevention)
- Services MAY depend on `app.utils.*` modules
- Repositories MAY depend on `app.utils.models` and `app.utils.database`

**Forbidden Dependencies**:
- Repositories MUST NOT depend on services
- Repositories MUST NOT depend on other repositories
- Services MUST NOT import from `app.routes.*`
- No circular dependencies between service modules

**Dependency Injection Pattern**:
```python
# In service constructor or function parameters
def __init__(self, user_repository: UserRepository = Depends(get_user_repository)):
    self.user_repository = user_repository
```
</dependency_hierarchy>

<error_handling_strategy>
**Service Layer Exceptions**:
- Raise domain-specific exceptions: `UserNotFoundError`, `InvalidAgentTimeError`
- Use result objects for success/failure states: `ServiceResult[T]`
- Log business rule violations at appropriate levels
- Never raise HTTPException or web framework exceptions

**Repository Layer Exceptions**:
- Handle database constraints and foreign key violations
- Convert SQLAlchemy exceptions to domain exceptions
- Ensure database connections are properly closed
- Use database transaction rollbacks on errors

**Exception Hierarchy Example**:
```python
class DomainException(Exception):
    """Base exception for domain errors"""
    pass

class UserNotFoundError(DomainException):
    """Raised when user does not exist"""
    pass
```
</error_handling_strategy>

<type_annotation_requirements>
**Function Signatures**:
- ALL function parameters must have type hints
- ALL return types must be explicitly annotated
- Use generic types for collections: `List[User]`, `Dict[str, Any]`
- Use Union types for optional returns: `Optional[User]` or `User | None`

**Import Standards for Types**:
```python
from typing import List, Dict, Optional, Union, Protocol
from app.utils.models import User, CreateUserRequest
from app.utils.common import ServiceResult
```

**Async Function Annotations**:
```python
async def get_user_by_id(user_id: int) -> Optional[User]:
async def create_users(users: List[CreateUserRequest]) -> List[User]:
```
</type_annotation_requirements>

<documentation_standards>
**Module-Level Docstrings**:
```python
"""
User Service Module

Handles all user-related business operations including:
- User registration and authentication
- Profile management and updates  
- User preference configuration
- Account deactivation and deletion

Dependencies:
- UserRepository for data persistence
- EmailService for notification sending
"""
```

**Function Documentation**:
- Document business rules and constraints
- Specify expected exceptions that may be raised
- Include usage examples for complex functions
- Document performance considerations for expensive operations
</documentation_standards>

<implementation_patterns>
**Service Result Pattern**:
```python
@dataclass
class ServiceResult[T]:
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Repository Query Builder Pattern**:
```python
class UserRepository:
    def build_user_query(self, filters: UserFilters) -> Select[User]:
        query = select(User).where(User.is_active == True)
        if filters.email:
            query = query.where(User.email.contains(filters.email))
        return query
```
</implementation_patterns>

<implementation_checklist>
Before considering any service domain complete:
- [ ] Domain folder created with required files and `__init__.py`
- [ ] Service module contains only business logic, no database operations
- [ ] Repository module handles all database operations with proper transactions
- [ ] All functions have complete type annotations
- [ ] Module docstring explains domain purpose and dependencies
- [ ] Domain exceptions defined and used appropriately
- [ ] No circular dependencies between services
- [ ] No HTTP concerns in service layer
- [ ] Proper dependency injection patterns implemented
- [ ] Service result objects used for error handling
- [ ] Repository uses SQLModel/SQLAlchemy correctly
- [ ] All database sessions properly managed and closed
</implementation_checklist>

<testing_strategy>
**Service Layer Testing**:
- Mock repository dependencies
- Test business logic in isolation
- Validate exception handling and error states
- Test cross-domain service interactions

**Repository Layer Testing**:
- Use test database with proper cleanup
- Test query correctness and performance
- Validate transaction rollback behavior
- Test constraint violation handling
</testing_strategy>
