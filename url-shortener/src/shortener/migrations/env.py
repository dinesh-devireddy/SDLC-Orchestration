from alembic import context
from shortener.models import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use python -m shortener init-db")
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
