"""Two-phase recovery demo: stop worker, --prepare, restart worker, --verify."""

import asyncio
import json
import sys
from uuid import uuid4

from neo4j import AsyncGraphDatabase
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from app.application.services.publication_processor import PublicationProcessor
from app.core.config import get_settings
from app.domain.entities import Post
from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
    MongoPublicationJobs,
)
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds


class InterruptedFeeds(RedisPublicationFeeds):
    def __init__(self, client, crash):
        super().__init__(client)
        self.crash = crash

    async def stage_batch(self, user_ids, post_id, score):
        await super().stage_batch(user_ids, post_id, score)
        if self.crash:
            raise asyncio.CancelledError("Simulated crash after Redis write, before cursor save")

    async def remove_batch(self, user_ids, post_id):
        raise ConnectionError("Redis unavailable during compensation")


async def main():
    s = get_settings()
    mongo = AsyncMongoClient(s.mongodb_url)
    db = mongo[s.mongodb_database]
    redis = Redis.from_url(s.redis_url)
    graph = AsyncGraphDatabase.driver(
        s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password.get_secret_value())
    )
    jobs = MongoPublicationJobs(db)
    try:
        if "--prepare" in sys.argv:
            author = uuid4()
            followers = [str(uuid4()) for _ in range(501)]
            async with graph.session() as session:
                result = await session.run(
                    "CREATE (a:User {id:$author}) WITH a UNWIND $ids AS id "
                    "CREATE (:User {id:id})-[:FOLLOWS]->(a)",
                    author=str(author),
                    ids=followers,
                )
                await result.consume()
            probes = []
            for crash in (True, False):
                job = await jobs.enqueue(
                    Post(user_id=author, text="P1 recovery probe", interests=("datos",)),
                    str(uuid4()),
                    None if crash else "redis_feed_partial",
                )
                processor = PublicationProcessor(
                    jobs, Neo4jSocialGraphRepository(graph), InterruptedFeeds(redis, crash)
                )
                try:
                    await processor.process(job)
                except (asyncio.CancelledError, ConnectionError):
                    pass
                saved = await jobs.get(job.operation.operation_id)
                assert saved is not None and saved.offset == 0
                assert saved.rollback == (not crash)
                assert await redis.zscore(f"feed:{followers[0]}", str(job.post.id)) is not None
                assert await redis.get(RedisPublicationFeeds.state_key(job.post.id)) != b"published"
                probes.append(
                    {
                        "operation_id": str(job.operation.operation_id),
                        "post_id": str(job.post.id),
                        "rollback": not crash,
                    }
                )
            await db.qa_p1_runs.replace_one(
                {"_id": "recovery-probe"},
                {"_id": "recovery-probe", "probes": probes, "followers": followers},
                upsert=True,
            )
            print("PREPARED: interrupted batch and interrupted compensation persisted in MongoDB")
            print(json.dumps(probes))
        else:
            from uuid import UUID

            run = await db.qa_p1_runs.find_one({"_id": "recovery-probe"})
            assert run is not None
            for probe in run["probes"]:
                expected = "compensated" if probe["rollback"] else "completed"
                for _ in range(200):
                    job = await jobs.get(UUID(probe["operation_id"]))
                    if job is not None and job.operation.status.value == expected:
                        break
                    await asyncio.sleep(0.1)
                assert job is not None and job.operation.status.value == expected
                document = await db.posts.find_one({"_id": probe["post_id"]})
                assert (document is None) == probe["rollback"]
                pipe = redis.pipeline(transaction=False)
                for user in run["followers"]:
                    pipe.zscore(f"feed:{user}", probe["post_id"])
                scores = await pipe.execute()
                assert all((score is None) == probe["rollback"] for score in scores)
                print("PASS: real worker restart recovered " + expected)
    finally:
        await graph.close()
        await mongo.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
