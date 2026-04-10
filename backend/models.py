from sqlalchemy import Column, String, Text, DateTime, Integer
from datetime import datetime
from database import Base

class Article(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text)
    author = Column(String)
    image_url = Column(Text)
    source_name = Column(String)
    source_url = Column(Text)
    category = Column(String)
    language = Column(String, default="en") # "en" or "hi"
    created_at = Column(DateTime, default=datetime.utcnow)
    score = Column(Integer, default=0)
    is_trending = Column(Integer, default=0) # 0 or 1

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "author": self.author,
            "image_url": self.image_url,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "category": self.category,
            "language": self.language,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "score": self.score,
            "is_trending": bool(self.is_trending)
        }

