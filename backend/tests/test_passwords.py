
"""Tests for RESQNET's Argon2id password security."""

from argon2 import PasswordHasher, Type

from passwords import (
    hash_password,
    verify_password,
    password_needs_rehash,
)


def test_password_is_hashed_with_argon2id():
    password = "example-test-password-123"

    stored_hash = hash_password(password)

    assert stored_hash != password
    assert stored_hash.startswith("$argon2id$")


def test_correct_password_is_accepted():
    password = "correct-test-password-123"
    stored_hash = hash_password(password)

    assert verify_password(password, stored_hash) is True


def test_incorrect_password_is_rejected():
    stored_hash = hash_password("correct-password")

    assert verify_password("wrong-password", stored_hash) is False


def test_malformed_hash_is_rejected():
    assert verify_password(
        "example-password",
        "this-is-not-an-argon2-hash",
    ) is False


def test_same_password_produces_different_salted_hashes():
    password = "same-password-for-two-users"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash

    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_outdated_hash_parameters_require_rehash():
    # Simulate a hash created with weaker parameters.
    older_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
        type=Type.ID,
    )

    old_hash = older_hasher.hash("example-password")
    current_hash = hash_password("example-password")

    assert password_needs_rehash(old_hash) is True
    assert password_needs_rehash(current_hash) is False
