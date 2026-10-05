from enum import StrEnum


class MongoCollection(StrEnum):
    POSTS = "posts"
    COMMENTS = "comments"
    REACTIONS = "reactions"
    CONVERSATIONS = "conversations"
    MESSAGES = "messages"

