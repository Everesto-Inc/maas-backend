"""Tests for pure utility functions — no DB, no network, no Oracle wallet."""
import hashlib
import re


# --- slugify logic (mirrors routers/auth.py _slugify) ---

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def test_slugify_basic():
    assert _slugify("Acme Corp") == "acme-corp"


def test_slugify_strips_special_chars():
    assert _slugify("Hello, World!") == "hello-world"


def test_slugify_collapses_hyphens():
    assert _slugify("foo---bar") == "foo-bar"


def test_slugify_trims_leading_trailing_hyphens():
    assert _slugify("  --hello--  ") == "hello"


def test_slugify_max_50_chars():
    long = "a" * 100
    assert len(_slugify(long)) <= 50


def test_slugify_numbers_preserved():
    assert _slugify("Client 42") == "client-42"


# --- hash_token (mirrors services/auth_service.py hash_token) ---

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def test_hash_token_is_deterministic():
    assert _hash_token("mytoken") == _hash_token("mytoken")


def test_hash_token_different_inputs_differ():
    assert _hash_token("token-a") != _hash_token("token-b")


def test_hash_token_is_hex_64_chars():
    result = _hash_token("any-token")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# --- plan VM limit logic (mirrors services/auth_service.py check_plan_vm_limit) ---

FREE_VM_LIMIT = 3


def _check_plan_vm_limit(plan: str, current_vm_count: int) -> bool:
    """Returns True if limit exceeded."""
    return plan == "free" and current_vm_count >= FREE_VM_LIMIT


def test_free_plan_under_limit():
    assert _check_plan_vm_limit("free", 2) is False


def test_free_plan_at_limit():
    assert _check_plan_vm_limit("free", 3) is True


def test_free_plan_over_limit():
    assert _check_plan_vm_limit("free", 10) is True


def test_pro_plan_no_limit():
    assert _check_plan_vm_limit("pro", 1000) is False


def test_enterprise_plan_no_limit():
    assert _check_plan_vm_limit("enterprise", 9999) is False
