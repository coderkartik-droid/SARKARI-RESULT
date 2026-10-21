"""Provider model allowlist and multi-account configuration registry.

The registry is the single source of truth for which provider/model pairs may be
selected and which credential each one is sent with.

Credentials are read from two sources:

* the project's ``.env`` file, parsed in *file order* with duplicate variable
  names preserved. A repeated ``OPENROUTER_API_KEY`` / ``OPENROUTER_MODEL``
  block therefore declares an additional account instead of overwriting the
  previous one. Parsing ``os.environ`` alone keeps only the last value of a
  repeated name, which is why several configured accounts used to collapse
  into a single model;
* the effective Django settings, including numbered ``*_API_KEY_2`` /
  ``*_MODEL_2`` variants for deployments that configure providers without an
  ``.env`` file.

The file is treated as authoritative for a provider only while the effective
settings still match it, so an explicit ``override_settings`` (or a shell
override) is never polluted by file contents.

Credentials never leave this module: public model dicts expose a stable
``id`` only, and routing resolves that id back to the credential server-side.
"""

import re
from pathlib import Path

from django.conf import settings

from . import availability

PROVIDER_SETTINGS = {
    "gemini": ("GEMINI_MODEL", "GEMINI_MODEL_EXPLICIT", "GEMINI_API_KEY"),
    "openai": ("OPENAI_MODEL", "OPENAI_MODEL_EXPLICIT", "OPENAI_API_KEY"),
    "openrouter": (
        "OPENROUTER_MODEL",
        "OPENROUTER_MODEL_EXPLICIT",
        "OPENROUTER_API_KEY",
    ),
    "grok": ("GROK_MODEL", "GROK_MODEL_EXPLICIT", "GROK_API_KEY"),
}

PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "openrouter": "OpenRouter",
    "grok": "Grok",
}

PROVIDER_ORDER = tuple(PROVIDER_SETTINGS)

_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,149}$")
_ENV_LINE_PATTERN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse_model_names(value):
    """Parse a comma-separated model allowlist, preserving order."""
    if not isinstance(value, str):
        return []
    names = []
    for candidate in value.split(","):
        name = candidate.strip()
        if name and name not in names:
            names.append(name)
    return names


def parse_env_occurrences(text):
    """Return every ``(name, value)`` pair in file order, duplicates included.

    Unlike ``os.environ`` this keeps *all* declarations, which is what allows a
    repeated provider block in one ``.env`` to describe several accounts.
    """
    occurrences = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE_PATTERN.match(raw_line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1].strip()
        occurrences.append((match.group(1), value))
    return occurrences


def blocks_from_env_occurrences(occurrences):
    """Pair each model declaration with the key declared most recently above it.

    Returns ``{provider: [(api_key, "model-a,model-b"), ...]}`` in file order.
    """
    blocks = {name: [] for name in PROVIDER_ORDER}
    current_key = {name: "" for name in PROVIDER_ORDER}
    for variable, value in occurrences:
        for provider_name in PROVIDER_ORDER:
            model_var, _, key_var = PROVIDER_SETTINGS[provider_name]
            if variable == key_var:
                current_key[provider_name] = value
            elif variable == model_var:
                blocks[provider_name].append((current_key[provider_name], value))
    return blocks


def _env_file_occurrences():
    """Read the configured ``.env`` file. An empty path disables scanning."""
    path = getattr(settings, "AI_MODEL_ENV_FILE", None)
    if path is None:
        path = str(Path(settings.BASE_DIR) / ".env")
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            return parse_env_occurrences(handle.read())
    except OSError:
        return []


def _authoritative_file_blocks(provider_name, file_blocks):
    """Return the provider's file blocks, or ``None`` when settings win."""
    model_var, explicit_var, _ = PROVIDER_SETTINGS[provider_name]
    if not getattr(settings, explicit_var, False):
        return None
    blocks = file_blocks.get(provider_name, [])
    if not blocks:
        return None
    effective = getattr(settings, model_var, "")
    if not isinstance(effective, str) or effective.strip() != blocks[-1][1].strip():
        return None  # the running value did not come from the file
    return blocks


def _settings_blocks(provider_name):
    """Read the effective settings, including numbered multi-account variants."""
    model_var, explicit_var, key_var = PROVIDER_SETTINGS[provider_name]
    if not getattr(settings, explicit_var, False):
        return []

    def read(name):
        value = getattr(settings, name, "")
        return value.strip() if isinstance(value, str) else ""

    blocks = [(read(key_var), read(model_var))]
    suffix = 2
    while True:
        extra_key = getattr(settings, f"{key_var}_{suffix}", None)
        extra_model = getattr(settings, f"{model_var}_{suffix}", None)
        if extra_key is None and extra_model is None:
            break
        blocks.append((read(f"{key_var}_{suffix}"), read(f"{model_var}_{suffix}")))
        suffix += 1
    return blocks


def _collect_blocks():
    """Collect, per provider, the account blocks that are actually running."""
    occurrences = _env_file_occurrences()
    file_blocks = blocks_from_env_occurrences(occurrences) if occurrences else None
    collected = {}
    for provider_name in PROVIDER_ORDER:
        blocks = None
        if file_blocks is not None:
            blocks = _authoritative_file_blocks(provider_name, file_blocks)
        collected[provider_name] = blocks if blocks is not None else _settings_blocks(provider_name)
    return collected


def _assign_identities(entries):
    """Give every entry a stable id, qualifying accounts that share a model."""
    totals = {}
    for entry in entries:
        totals[(entry["provider"], entry["model"])] = (
            totals.get((entry["provider"], entry["model"]), 0) + 1
        )
    seen = {}
    for entry in entries:
        group = (entry["provider"], entry["model"])
        base = f"{entry['provider']}:{entry['model']}"
        if totals[group] == 1:
            entry["id"] = base
            entry["label"] = f"{entry['provider_label']} — {entry['model']}"
            continue
        seen[group] = seen.get(group, 0) + 1
        entry["id"] = f"{base}#{seen[group]}"
        entry["label"] = (
            f"{entry['provider_label']} — {entry['model']} (account {seen[group]})"
        )


def build_registry(blocks):
    """Build the registry from ``{provider: [(api_key, "models"), ...]}``."""
    entries = []
    errors = []
    seen = set()
    for provider_name in PROVIDER_ORDER:
        label = PROVIDER_LABELS[provider_name]
        for account_number, (api_key, raw_models) in enumerate(
            blocks.get(provider_name, []), start=1
        ):
            models = parse_model_names(raw_models)
            if not models:
                if api_key:
                    errors.append(
                        f"{label} account {account_number} declares a key but no model, "
                        "so it is not registered."
                    )
                continue
            for model_id in models:
                if not _MODEL_ID_PATTERN.fullmatch(model_id):
                    errors.append(
                        f"{label} entry '{model_id[:40]}' is not a valid model ID and "
                        "was not registered."
                    )
                    continue
                fingerprint = (provider_name, model_id, api_key)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                entries.append(
                    {
                        "provider": provider_name,
                        "provider_label": label,
                        "model": model_id,
                        "api_key": api_key,
                        "account": account_number,
                    }
                )
    _assign_identities(entries)
    return entries, errors


def get_registry():
    """Return every registered configuration, credentials included.

    Internal use only: callers must never serialise ``api_key``.
    """
    entries, _ = build_registry(_collect_blocks())
    return entries


def _public_model(entry):
    """Credential-free view of a registry entry, safe to send to the browser."""
    configured = bool(entry["api_key"])
    status = "unknown" if configured else "missing_api_key"
    return {
        "id": entry["id"],
        "provider": entry["provider"],
        "provider_label": entry["provider_label"],
        "model": entry["model"],
        "label": entry["label"],
        "configured": configured,
        "status": status,
        "availability": availability.label_for(status),
        "message": (
            "Availability has not been checked."
            if configured
            else f"{entry['provider_label']} API key is missing for this configuration."
        ),
    }


def get_model_configuration():
    """Return public provider/model pairs and safe configuration diagnostics."""
    entries, errors = build_registry(_collect_blocks())
    return [_public_model(entry) for entry in entries], errors


def get_configured_models(provider_name):
    """Return the distinct model IDs configured for exactly one provider."""
    provider_name = (
        provider_name.strip().lower() if isinstance(provider_name, str) else ""
    )
    models = []
    for entry in get_registry():
        if entry["provider"] == provider_name and entry["model"] not in models:
            models.append(entry["model"])
    return models


def resolve_configuration(provider_name, model_id=None, config_id=None):
    """Resolve a request to exactly one registry entry, or ``None``.

    ``config_id`` selects a specific account. An unknown id never falls back to
    another account or model: the caller must report the failure instead.
    """
    entries = get_registry()
    if config_id is not None:
        if not isinstance(config_id, str) or len(config_id) > 200:
            return None
        for entry in entries:
            if entry["id"] == config_id:
                return entry
        return None
    if not isinstance(provider_name, str):
        return None
    provider_name = provider_name.strip().lower()
    if model_id is None:
        for entry in entries:
            if entry["provider"] == provider_name:
                return entry
        return None
    if not isinstance(model_id, str):
        return None
    model_id = model_id.strip()
    for entry in entries:
        if entry["provider"] == provider_name and entry["model"] == model_id:
            return entry
    return None
