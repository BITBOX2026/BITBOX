import os


# Unit tests must never depend on a developer's local .env real-mode settings.
os.environ["USE_MOCK_EXTERNALS"] = "true"
os.environ["API_AUTH_TOKEN"] = ""
os.environ["RATE_LIMIT_ENABLED"] = "false"
