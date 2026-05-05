import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 1. บังคับให้ Python รู้จักโฟลเดอร์ app 
# (สำคัญมาก! เพื่อให้ import app.models ได้)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2. นำเข้า Base (ที่มี MetaData ของตารางทั้งหมด) และ URL
from app.models import Base
from app.database import DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 3. เซ็ตค่า Database URL ให้กับ Alembic
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. ชี้เป้าหมายให้ Alembic รู้จักโครงสร้างตาราง (จุดที่ทำให้เกิด Error เมื่อกี้)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # ใช้ค่า Configuration ที่เราตั้งไว้ด้านบน
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()