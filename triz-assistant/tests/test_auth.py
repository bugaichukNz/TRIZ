"""Тесты JWT-аутентификации без сети."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from backend.auth import ALGORITHM, create_access_token, decode_access_token
from backend.config import settings


class TestAccessToken:
    def test_create_decode_roundtrip(self) -> None:
        token = create_access_token("user-42", "tester")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-42"
        assert payload["username"] == "tester"
        assert "exp" in payload

    def test_decode_preserves_custom_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = "another-pytest-secret-key-for-jwt"
        monkeypatch.setattr(settings, "jwt_secret", secret)
        token = jwt.encode(
            {
                "sub": "u1",
                "username": "alice",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            secret,
            algorithm=ALGORITHM,
        )
        payload = decode_access_token(token)
        assert payload["sub"] == "u1"
        assert payload["username"] == "alice"

    def test_expired_token_raises_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = settings.jwt_secret
        expired = jwt.encode(
            {
                "sub": "user-1",
                "username": "bob",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            secret,
            algorithm=ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(expired)
        assert exc_info.value.status_code == 401
        assert "токен" in exc_info.value.detail.lower()

    def test_invalid_signature_raises_401(self) -> None:
        token = create_access_token("user-1", "bob")
        tampered = token[:-5] + "xxxxx"
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401

    def test_malformed_token_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401
