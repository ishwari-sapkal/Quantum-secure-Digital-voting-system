from pymongo import MongoClient

try:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["voting_system"]

    users = db["users"]
    votes = db["votes"]

    print("MongoDB connected successfully!")
    print("Collections:", db.list_collection_names())

except Exception as e:
    print("MongoDB connection failed")
    print(e)
