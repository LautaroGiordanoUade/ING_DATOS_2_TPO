import argparse
import asyncio
import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SeedOptions:
    users: int
    posts: int
    messages: int
    seed: int


async def seed(options: SeedOptions) -> None:
    random.seed(options.seed)
    # TODO(TP): Implementar dataset realista, carga por lotes y volumen mínimo de 50.000.
    # TODO(TP): Mantener UUID compartidos y orden seguro entre MongoDB, Neo4j y Redis.
    logger.info(
        "Seed skeleton ready: users=%s posts=%s messages=%s seed=%s",
        options.users,
        options.posts,
        options.messages,
        options.seed,
    )


def parse_args() -> SeedOptions:
    parser = argparse.ArgumentParser(description="Generador reproducible de datos de prueba")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--posts", type=int, default=1_000)
    parser.add_argument("--messages", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    return SeedOptions(args.users, args.posts, args.messages, args.seed)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed(parse_args()))

