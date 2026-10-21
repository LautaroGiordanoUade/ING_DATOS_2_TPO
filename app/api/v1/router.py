from fastapi import APIRouter

from app.api.v1.routers import (
    accounts,
    feeds,
    interactions,
    messages,
    moderation,
    posts,
    problems,
    social,
    users,
)

api_router = APIRouter()
api_router.include_router(problems.router, prefix="/problems", tags=["problems"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(social.router, prefix="/social", tags=["social"])
api_router.include_router(feeds.router, prefix="/feeds", tags=["feeds"])
api_router.include_router(interactions.router, prefix="/interactions", tags=["interactions"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(moderation.router, prefix="/moderation", tags=["moderation"])


api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
