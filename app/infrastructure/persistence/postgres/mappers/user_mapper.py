from app.domain.entities import User
from app.domain.entities.models import AccountStatus, AccountType
from app.infrastructure.persistence.postgres.models import UserModel


def user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        username=model.username,
        full_name=model.full_name,
        email=model.email,
        password_hash=model.password_hash,
        biography=model.biography,
        account_type=AccountType(model.account_type),
        account_status=AccountStatus(model.account_status),
        registered_at=model.registered_at,
    )

