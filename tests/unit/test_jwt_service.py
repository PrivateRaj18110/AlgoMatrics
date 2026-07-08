from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from algo_platform.shared.domain.errors import AuthenticationFailed
from algo_platform.shared.infrastructure.jwt_service import JwtService


def make_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def make_service(ttl: int = 900) -> JwtService:
    private_pem, public_pem = make_keypair()
    return JwtService(
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        issuer="algo-matrics",
        audience="algo-matrics-api",
        access_ttl_seconds=ttl,
    )


def test_issue_and_verify_roundtrip() -> None:
    service = make_service()
    user_id, session_id = uuid4(), uuid4()
    issued = service.issue(
        user_id=user_id,
        session_id=session_id,
        email="user@example.com",
        organization_id=None,
        role=None,
        is_platform_admin=True,
    )
    claims = service.verify(issued.token)
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.email == "user@example.com"
    assert claims.is_platform_admin is True
    assert claims.organization_id is None
    assert claims.token_id == issued.token_id


def test_verify_rejects_garbage_and_cross_service_tokens() -> None:
    service_a = make_service()
    service_b = make_service()
    issued = service_a.issue(
        user_id=uuid4(),
        session_id=uuid4(),
        email="e@x.co",
        organization_id=None,
        role=None,
        is_platform_admin=False,
    )
    with pytest.raises(AuthenticationFailed):
        service_b.verify(issued.token)  # different keypair
    with pytest.raises(AuthenticationFailed):
        service_a.verify("not-a-token")
