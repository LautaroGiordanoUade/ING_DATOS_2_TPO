from collections import Counter

import pytest

from app.tools.dataset import Dataset, SeedOptions


def small(**changes: int) -> Dataset:
    return Dataset(
        SeedOptions(
            **{
                "users": 12,
                "posts": 40,
                "comments": 20,
                "reactions": 80,
                "messages": 30,
                "conversations": 4,
                "reports": 3,
                **changes,
            }
        )
    )


def test_reproducible_across_batch_sizes_without_global_rng_changes() -> None:
    import random

    random.seed(35)
    state = random.getstate()
    assert small(batch_size=1).checksum() == small(batch_size=500).checksum()
    assert small(seed=43).checksum() != small(seed=42).checksum()
    assert random.getstate() == state


def test_uuid_references_reaction_uniqueness_and_no_self_follows() -> None:
    data = small()
    users, posts = set(data.users), set(data.posts)
    pairs = []
    for item in data.interaction_documents("reaction", 80):
        assert item["post_id"] in posts and item["user_id"] in users
        pairs.append((item["post_id"], item["user_id"]))
    assert len(set(pairs)) == len(pairs)
    for edge in data.relationships():
        assert edge["f"] != edge["a"]
        assert edge["f"] in users and edge["a"] in users
        assert {edge["f"], edge["a"]} != {data.users[2], data.users[5]}
    assert any(edge["status"] == "pending" for edge in data.relationships())


def test_group_members_senders_and_sequences_are_consistent() -> None:
    data = small()
    groups = {doc["_id"]: doc for doc in data.group_documents()}
    sequences: dict[str, list[int]] = {gid: [] for gid in groups}
    for message in data.message_documents():
        group = groups[message["conversation_id"]]
        assert message["sender_id"] in group["participant_ids"]
        assert message["created_at"] > group["created_at"]
        sequences[group["_id"]].append(message["sequence"])
    for gid, group in groups.items():
        assert sequences[gid] == list(range(1, group["sequence"] + 1))
        assert len(group["participant_ids"]) == len(set(group["participant_ids"]))
        assert 2 <= len(group["participant_ids"]) <= 20
        assert all(0 <= seq <= group["sequence"] for seq in group["read_through"].values())


def test_default_is_50000_in_one_entity_and_supports_large_audiences() -> None:
    data = Dataset(SeedOptions())
    counts = Counter(edge["a"] for edge in data.relationships() if edge["status"] == "accepted")
    assert len(data.posts) == 50_000
    assert counts[data.users[0]] >= 1000
    assert {user["role"] for user in data.user_documents()} == {"user", "moderator", "admin"}
    assert len({user["username"] for user in data.user_documents()}) == 1200


@pytest.mark.parametrize(
    "changes",
    [
        {"users": 1},
        {"posts": 0},
        {"comments": -1},
        {"batch_size": 0},
        {"reactions": 999_999},
        {"reports": 100},
        {"conversations": 15},
    ],
)
def test_rejects_invalid_sizes(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        small(**changes)


async def test_cli_plan_does_not_connect_or_need_a_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse
    import json
    from dataclasses import asdict

    from app.tools import seed_data

    args = argparse.Namespace(
        **asdict(small().options), apply=False, verify=False, allow_small=False
    )
    monkeypatch.setattr(seed_data, "parse_args", lambda: args)

    def forbidden() -> None:
        raise AssertionError("El plan no debe conectarse a motores")

    monkeypatch.setattr(seed_data, "get_settings", forbidden)
    await seed_data.run()
    assert json.loads(capsys.readouterr().out)["status"] == "plan_only"


@pytest.mark.parametrize("production", [True, False])
async def test_cli_refuses_production_or_small_load_without_opt_in(
    monkeypatch: pytest.MonkeyPatch, production: bool
) -> None:
    import argparse
    from dataclasses import asdict

    from app.core.config import Settings
    from app.tools import seed_data

    args = argparse.Namespace(
        **asdict(small().options), apply=True, verify=False, allow_small=False
    )
    monkeypatch.setattr(seed_data, "parse_args", lambda: args)
    settings = Settings(app_env="production" if production else "testing", auth_secret="x" * 40)
    monkeypatch.setattr(seed_data, "get_settings", lambda: settings)
    with pytest.raises((RuntimeError, ValueError), match="development|50000"):
        await seed_data.run()
