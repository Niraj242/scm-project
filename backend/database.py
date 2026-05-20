from sqlalchemy.orm import sessionmaker, declarative_base
import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("postgresql://neondb_owner:npg_EeyF0hi3JRcV@ep-wild-resonance-aoturwvf.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")

if not DATABASE_URL:
    raise Exception("DATABASE_URL not set")

engine = create_engine(
    DATABASE_URL,
    echo=True  # shows SQL queries in terminal (good for learning/debug)
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
