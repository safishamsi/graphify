"""Tests for _is_sensitive(): the file-skip heuristic that drops files
expected to contain secrets. Two correctness properties:

  1. Source-code files are never dropped by the generic keyword filter,
     because source IS code, not credential storage. A file like
     'password-reset.ts' is a code module — graphify should index it.

  2. Specific patterns (.env, .pem, id_rsa, .netrc, etc.) keep applying
     to all files, so a config or credential file with one of those
     names is still flagged regardless of code/data classification.
"""

from pathlib import Path

from graphify.detect import _is_sensitive


def _f(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("placeholder", encoding="utf-8")
    return p


# ── Source code is never dropped by the keyword filter ──────────────────────


def test_password_in_ts_filename_not_sensitive(tmp_path):
    """Real reproducer: 'password-reset.ts' is a TS module that handles the
    user-facing password-reset flow. It contains email-template code, not
    secrets. Must not be dropped."""
    assert not _is_sensitive(_f(tmp_path, "password-reset.ts"))


def test_token_in_ts_model_filename_not_sensitive(tmp_path):
    """Real reproducer: 'AuthOauthAccessToken.model.ts' is a Sequelize
    model definition. Code, not credentials."""
    assert not _is_sensitive(_f(tmp_path, "AuthOauthAccessToken.model.ts"))


def test_token_in_test_helper_filename_not_sensitive(tmp_path):
    """Real reproducer: 'test.search-tokenizer.ts' — 'tokenizer' contains
    'token' as a substring. With word boundaries, it doesn't match anyway,
    but the source-code exemption makes it doubly safe."""
    assert not _is_sensitive(_f(tmp_path, "test.search-tokenizer.ts"))


def test_credential_in_python_filename_not_sensitive(tmp_path):
    """Common pattern: a Python module that handles credentials at the
    application level (validation, storage, refresh) is still code."""
    assert not _is_sensitive(_f(tmp_path, "credential_validator.py"))


def test_secret_in_javascript_filename_not_sensitive(tmp_path):
    """Same logic for JS: a module file is code, not raw secrets."""
    assert not _is_sensitive(_f(tmp_path, "secret-handler.js"))


def test_jwt_token_validator_java_not_sensitive(tmp_path):
    """Java source — a JWT token validator is auth code, not a credential."""
    assert not _is_sensitive(_f(tmp_path, "JwtTokenValidator.java"))


def test_password_handling_svelte_component_not_sensitive(tmp_path):
    """Svelte component for password-related UI is still source code."""
    assert not _is_sensitive(_f(tmp_path, "password-input.svelte"))


def test_keyword_in_typescript_declaration_not_sensitive(tmp_path):
    """TypeScript declaration files (.d.ts) are interface/type definitions."""
    assert not _is_sensitive(_f(tmp_path, "auth-token-types.d.ts"))


# ── Specific extension/name patterns still apply to all files ───────────────


def test_dotenv_still_flagged(tmp_path):
    """The most important credential-storage file pattern."""
    assert _is_sensitive(_f(tmp_path, ".env"))
    assert _is_sensitive(_f(tmp_path, ".env.local"))
    assert _is_sensitive(_f(tmp_path, ".env.production"))


def test_envrc_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, ".envrc"))


def test_pem_certificate_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, "server.pem"))
    assert _is_sensitive(_f(tmp_path, "key.p12"))
    assert _is_sensitive(_f(tmp_path, "site.cert"))


def test_ssh_key_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, "id_rsa"))
    assert _is_sensitive(_f(tmp_path, "id_ed25519.pub"))


def test_netrc_pgpass_htpasswd_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, ".netrc"))
    assert _is_sensitive(_f(tmp_path, ".pgpass"))
    assert _is_sensitive(_f(tmp_path, ".htpasswd"))


def test_cloud_credential_files_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, "aws_credentials"))
    assert _is_sensitive(_f(tmp_path, "gcloud_credentials.json"))
    assert _is_sensitive(_f(tmp_path, "service.account.json"))


# ── Non-code files with keyword still flagged (data files store secrets) ────


def test_secrets_json_still_flagged(tmp_path):
    """A JSON file literally named 'secrets.json' is data, plausibly secret
    storage. The generic keyword filter still applies to non-code files."""
    assert _is_sensitive(_f(tmp_path, "secrets.json"))


def test_credentials_yaml_still_flagged(tmp_path):
    """YAML configs named for credentials are likely real credential storage."""
    assert _is_sensitive(_f(tmp_path, "database-credentials.yml"))


def test_password_txt_still_flagged(tmp_path):
    """Plaintext 'password.txt' is the canonical bad-practice secret file."""
    assert _is_sensitive(_f(tmp_path, "password.txt"))


def test_token_in_data_file_still_flagged(tmp_path):
    assert _is_sensitive(_f(tmp_path, "api-token.json"))


# ── Word-boundary correctness on data files ─────────────────────────────────


def test_secretary_in_data_file_not_flagged(tmp_path):
    """'secretary' contains 'secret' but isn't a real word match. Word
    boundaries reject it."""
    assert not _is_sensitive(_f(tmp_path, "secretary-notes.txt"))


def test_tokenizer_in_data_file_not_flagged(tmp_path):
    """'tokenizer' has 'token' as a substring without a closing word boundary."""
    assert not _is_sensitive(_f(tmp_path, "tokenizer-config.json"))


def test_passwordless_in_data_file_not_flagged(tmp_path):
    """'passwordless' is a real word that isn't 'password'."""
    assert not _is_sensitive(_f(tmp_path, "passwordless-auth-rfc.md"))


def test_credentialing_in_data_file_not_flagged(tmp_path):
    """'credentialing' contains 'credential' without trailing boundary."""
    assert not _is_sensitive(_f(tmp_path, "medical-credentialing-rules.txt"))


# ── Mixed: code file with extension that ALSO matches a specific pattern ────


def test_pem_file_extension_overrides_code_check(tmp_path):
    """Even if someone manages to have a 'foo.ts.pem' file, the .pem
    extension pattern triggers regardless of code-extension exemption.
    The exemption only applies to the keyword pattern."""
    assert _is_sensitive(_f(tmp_path, "foo.ts.pem"))


def test_env_dotfile_still_flagged_alongside_code(tmp_path):
    """A '.env.ts' would be unusual but the .env pattern is structural."""
    # .suffix is .ts, but the .env pattern matches anywhere in the name
    # via the leading dot anchor. This file IS treated as sensitive.
    assert _is_sensitive(_f(tmp_path, ".env.ts"))


# ── Subprojects: works regardless of where the file lives ───────────────────


def test_keyword_in_nested_path_does_not_affect_classification(tmp_path):
    """Nested paths shouldn't change the verdict — only the filename matters
    after the issue 436 fix that removed full-path matching."""
    f = tmp_path / "src" / "lib" / "server" / "auth" / "password-reset.ts"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("export const x = 1")
    assert not _is_sensitive(f)


def test_directory_named_secretary_does_not_block_code_inside(tmp_path):
    """The literal reproducer from the original directory-name bug:
    a project under a path containing 'secret' as a substring of a real word."""
    f = tmp_path / "AISecretary" / "Services" / "Foo.swift"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// swift code")
    assert not _is_sensitive(f)
