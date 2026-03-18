from __future__ import annotations

import os

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "project1")

client = MongoClient(MONGODB_URL)
database: Database = client[MONGODB_DB_NAME]
users_collection: Collection = database["users"]
learning_plans_collection: Collection = database["learning_plans"]

users_collection.create_index("email", unique=True)
learning_plans_collection.create_index([("email", 1), ("plan_date", 1)], unique=True)
