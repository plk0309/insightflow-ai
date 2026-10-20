from app.core.security import hash_password, verify_password


def test_password_hash_is_not_plain_text():
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")


def test_correct_password_verifies():
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_wrong_password_fails():
    hashed = hash_password("TestPassword123!")

    assert verify_password("WrongPassword", hashed) is False


def test_same_password_produces_different_hashes():
    password = "TestPassword123!"

    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)