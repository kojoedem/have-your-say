import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, inspect, text  # type: ignore[import]
from sqlalchemy.orm import declarative_base, sessionmaker, relationship  # type: ignore[import]

#this is the database
DATABASE_URL = "sqlite:///have_your_say.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    telegram_chat_id = Column(String, unique=True, index=True, nullable=True)
    username = Column(String, nullable=True)
    alias = Column(String, nullable=True)
    belief = Column(String, nullable=True)
    otp_code = Column(String, nullable=True)
    otp_expires = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    session_token = Column(String, unique=True, index=True, nullable=True)

    topics = relationship("Topic", back_populates="author")
    comments = relationship("Comment", back_populates="author")

class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    location = Column(String, nullable=True)  # Location (e.g., country/city) when topic is posted
    allow_download = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, default=lambda: datetime.now(timezone.utc) + timedelta(hours=12))

    author = relationship("User", back_populates="topics")
    comments = relationship("Comment", back_populates="topics", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    text = Column(String, nullable=False)
    location = Column(String, nullable=True)  # Location (e.g. country, city) when commenting
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topics = relationship("Topic", back_populates="comments")
    author = relationship("User", back_populates="comments")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Comment", back_populates="replies", remote_side=[id])

def init_db():
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns_info = inspector.get_columns('users')
        columns = [col['name'] for col in columns_info]
        phone_info = next((col for col in columns_info if col['name'] == 'phone'), None)

        is_phone_not_nullable = phone_info and not phone_info.get('nullable', True)

        if 'email' not in columns or 'telegram_chat_id' not in columns or is_phone_not_nullable:
            # Recreate table strategy to preserve constraints and add columns cleanly
            with engine.begin() as conn:
                # 1. Disable foreign key checks temporarily
                conn.execute(text("PRAGMA foreign_keys=OFF"))

                # 2. Rename existing table
                conn.execute(text("ALTER TABLE users RENAME TO users_old"))

                # 3. Create the new users table using Base metadata
                Base.metadata.create_all(bind=engine)

                # 4. Copy data from old table to new table
                old_cols = [c for c in columns if c in ['id', 'phone', 'username', 'alias', 'belief', 'otp_code', 'otp_expires', 'is_verified', 'session_token']]
                old_cols_str = ", ".join(old_cols)
                conn.execute(text(f"INSERT INTO users ({old_cols_str}) SELECT {old_cols_str} FROM users_old"))

                # 5. Drop old table
                conn.execute(text("DROP TABLE users_old"))

                # 6. Re-enable foreign key checks
                conn.execute(text("PRAGMA foreign_keys=ON"))
        else:
            Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

    # Now handle topics table migration
    inspector = inspect(engine)
    if "topics" in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('topics')]
        if 'allow_download' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE topics ADD COLUMN allow_download BOOLEAN DEFAULT 1"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
