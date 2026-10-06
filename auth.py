"""Autenticação da API móvel: bcrypt para senhas e JWT para sessões."""
from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import os

import bcrypt
import jwt
from flask import g, request

JWT_SECRET = os.environ.get("SOUNDML_JWT_SECRET", "dev-only-change-this-secret-before-production-2026")
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = int(os.environ.get("SOUNDML_JWT_TTL_HOURS", "12"))


def hash_password(password):
    if not password or len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, stored_hash):
    if not password or not stored_hash:
        return False
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    # Compatibilidade de migração: hashes legados são atualizados no login.
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash


def is_legacy_hash(stored_hash):
    return not stored_hash.startswith(("$2a$", "$2b$", "$2y$"))


def issue_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "empresa_id": user["empresa_id"],
        "perfil": user["perfil"],
        "iat": now,
        "exp": now + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return {"ok": False, "error": "Token Bearer obrigatório"}, 401
        try:
            g.auth = jwt.decode(header[7:].strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return {"ok": False, "error": "Token expirado"}, 401
        except jwt.InvalidTokenError:
            return {"ok": False, "error": "Token inválido"}, 401
        return view(*args, **kwargs)
    return wrapped
