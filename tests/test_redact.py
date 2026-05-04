from daylee.redact import is_env_path, redact_text


def test_aws_key():
    assert "[REDACTED-AWS-KEY]" in redact_text("token AKIAABCDEFGHIJKLMNOP end")


def test_github_pat():
    raw_token = "ghp_" + "A" * 36
    assert raw_token not in redact_text(f"my {raw_token} here")


def test_slack_token():
    assert "[REDACTED-SLACK-TOKEN]" in redact_text("xoxb-1-2-deadbeef")


def test_jwt():
    text = "Bearer eyJabcdefghij.eyJklmnopqrst.signaturevalue"
    assert "eyJabc" not in redact_text(text)


def test_pem_block():
    pem = (
        "before -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAabcdef\n"
        "-----END RSA PRIVATE KEY----- after"
    )
    out = redact_text(pem)
    assert "MIIE" not in out
    assert "[REDACTED-PRIVATE-KEY]" in out


def test_truncates_to_2kb():
    out = redact_text("x" * 5000)
    # 2KB limit + ellipsis suffix
    assert len(out.encode("utf-8")) <= 2048 + len("…".encode("utf-8"))


def test_returns_none_for_none_input():
    assert redact_text(None) is None
    assert redact_text("") == ""


def test_is_env_path():
    assert is_env_path(".env")
    assert is_env_path("project/.env.local")
    assert is_env_path("secrets.yaml")
    assert not is_env_path("src/main.py")
