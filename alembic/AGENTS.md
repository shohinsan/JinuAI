# Alembic Migration Implementation Rules

<migration_file_structure>
**Required Imports** (in this exact order):
```python
"""Add user authentication system

Revision ID: 001_add_user_auth
Revises: 
Create Date: 2024-01-15 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql
from typing import Sequence, Union

# revision identifiers, used by Alembic
revision: str = '001_add_user_auth'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Mandatory Functions**:
- `upgrade() -> None`: Defines forward migration operations
- `downgrade() -> None`: Defines complete rollback operations
- Both functions must be complete and tested

**File Location**: All migrations auto-generated in `alembic/versions/`
**Naming Convention**: `{revision_number}_{descriptive_name}.py`
</migration_file_structure>

<migration_workflow>
**Development Process**:
1. **Generate Migration**:
   ```bash
   alembic revision --autogenerate -m "descriptive_name"
   ```

2. **Review Generated File**:
   - Check all table and column definitions
   - Verify foreign key relationships
   - Ensure proper indexes are created
   - Add any custom data transformations needed

3. **Test Migration Locally**:
   ```bash
   # Apply migration
   alembic upgrade head
   
   # Test application functionality
   pytest tests/
   
   # Test rollback
   alembic downgrade -1
   
   # Re-apply to ensure idempotency
   alembic upgrade head
   ```

4. **Validate on Staging**:
   - Apply to staging database with production-like data
   - Run full test suite
   - Verify application performance
   - Test rollback scenario

5. **Production Deployment**:
   - Schedule maintenance window if needed
   - Backup database before migration
   - Apply migration during low-traffic period
   - Monitor application logs and performance
</migration_workflow>

<command_reference>
**Essential Commands**:
```bash
# Generate new migration
alembic revision --autogenerate -m "add_user_authentication"

# Apply all pending migrations
alembic upgrade head

# Apply specific migration
alembic upgrade 001_add_user_auth

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 001_add_user_auth

# Show current database revision
alembic current

# Show migration history
alembic history --verbose

# Show pending migrations
alembic heads

# Generate SQL without applying
alembic upgrade head --sql

# Mark migration as applied without running
alembic stamp head
```

**Emergency Commands**:
```bash
# Force database to specific revision (dangerous!)
alembic stamp revision_id

# Show raw SQL that would be executed
alembic upgrade +1 --sql

# Validate current database state
alembic check
```
</command_reference>

