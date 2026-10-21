# AI Assistant Setup Guide

This guide explains how to configure and use the AI Assistant for the Sarkari Result Django project.

## Supported Providers

The AI Assistant supports three AI providers, selectable via environment variables:

### 1. Google Gemini (Default)

**Stable Model:** `gemini-3.8-flash` (Generally Available, no shutdown date announced)

**Official Documentation:**
- Models: https://ai.google.dev/gemini-api/docs/models
- Changelog: https://ai.google.dev/gemini-api/docs/changelog
- Deprecations: https://ai.google.dev/gemini-api/docs/deprecations

**How to Get API Key:**
1. Visit https://aistudio.google.com/
2. Sign in with your Google account
3. Click "Get API Key" in the left sidebar
4. Create a new project or select an existing one
5. Copy the API key (starts with a letter/number sequence)

**Pricing:**
- Free tier available with generous limits
- Paid tier based on token usage
- Check pricing at: https://ai.google.dev/pricing

**Default Configuration:**
```
AI_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.8-flash
```

### 2. OpenAI

**Stable Models:**
- `gpt-4o-mini` (recommended, cost-effective)
- `gpt-4o` (higher quality, more expensive)

**Official Documentation:**
- Models: https://developers.openai.com/api/docs/models
- GPT-4o: https://developers.openai.com/api/docs/models/gpt-4o
- GPT-4o Mini: https://developers.openai.com/api/docs/models/gpt-4o-mini

**How to Get API Key:**
1. Visit https://platform.openai.com/api-keys
2. Sign in or create an OpenAI account
3. Click "Create new secret key"
4. Copy the API key (starts with `sk-`)

**Pricing:**
- Pay-as-you-go based on token usage
- GPT-4o Mini: ~$0.15/1M input tokens, $0.60/1M output tokens
- GPT-4o: ~$2.5/1M input tokens, $10/1M output tokens
- Check pricing at: https://openai.com/pricing

**Default Configuration:**
```
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

### 3. OpenRouter

**Model Access:** 400+ models via single API endpoint

**Official Documentation:**
- Quickstart: https://openrouter.ai/docs/quickstart
- Models: https://openrouter.ai/docs/guides/overview/models
- API Reference: https://openrouter.ai/docs/api/api-reference

**How to Get API Key:**
1. Visit https://openrouter.ai/keys
2. Sign in or create an account
3. Create a new API key
4. Copy the API key (starts with `sk-or-`)

**Pricing:**
- Aggregates pricing from multiple providers
- Pay-as-you-go based on model selection
- Check model-specific pricing at: https://openrouter.ai/models

**Default Configuration:**
```
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `google-genai>=1.0.0` (for Gemini)
- `openai>=1.0.0` (for OpenAI and OpenRouter)

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and set your chosen provider's configuration:

**For Gemini (Recommended):**
```bash
AI_ENABLED=True
AI_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
```

**For OpenAI:**
```bash
AI_ENABLED=True
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your_actual_openai_api_key
OPENAI_MODEL=gpt-4o-mini
```

**For OpenRouter:**
```bash
AI_ENABLED=True
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your_actual_openrouter_api_key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

### 3. Optional Configuration

Adjust these settings in `.env` as needed:

```bash
# Request timeout in seconds (default: 60)
AI_TIMEOUT_SECONDS=60

# Maximum output tokens (default: 1024)
AI_MAX_OUTPUT_TOKENS=1024

# Maximum message length in characters (default: 4000)
AI_MAX_MESSAGE_LENGTH=4000

# Maximum conversation history messages (default: 10)
AI_MAX_HISTORY_MESSAGES=10

# Rate limiting: requests per minute per user (default: 15)
AI_RATE_LIMIT_PER_MINUTE=15

# Rate limiting: daily requests per user (default: 20)
AI_DAILY_REQUEST_LIMIT=20
```

## Running the Application

### Development

```bash
python manage.py runserver
```

The AI Assistant will be available at:
- Chat endpoint: `/api/ai/chat/` (POST, requires authentication)
- Job search: `/api/ai/jobs/` (GET/POST, requires authentication)
- Status: `/api/ai/status/` (GET, requires authentication)

### Production

1. Set production environment variables:
```bash
DJANGO_SECRET_KEY=your_secure_secret_key
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_ENGINE=django.db.backends.postgresql
DB_NAME=your_database
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=5432
```

2. Run migrations:
```bash
python manage.py migrate
```

3. Use a production WSGI server (e.g., gunicorn):
```bash
gunicorn config.wsgi:application
```

## Switching Providers

To switch between providers, simply change `AI_PROVIDER` and the corresponding API key/model in `.env`:

**From Gemini to OpenAI:**
```bash
# Change in .env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your_openai_key
OPENAI_MODEL=gpt-4o-mini
# You can leave or remove GEMINI_API_KEY
```

**From OpenAI to OpenRouter:**
```bash
# Change in .env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your_openrouter_key
OPENROUTER_MODEL=openai/gpt-4o-mini
# You can leave or remove OPENAI_API_KEY
```

No code changes required - the provider is selected automatically based on `AI_PROVIDER`.

## Testing

Run the AI Assistant tests:

```bash
python manage.py test ai_assistant.tests
```

Tests cover:
- Provider selection
- Configuration validation
- Missing API key behavior
- Disabled AI behavior
- Mocked provider responses
- Rate limiting (real implementation tested)
- Error handling
- Secret redaction

All external API calls are mocked in tests, so no API keys or costs are incurred.

## Troubleshooting

### AI Assistant shows "disabled"

**Solution:** Set `AI_ENABLED=True` in `.env`

### AI Assistant shows "unconfigured" with missing key message

**Solution:** 
- Ensure the API key for your selected provider is set in `.env`
- Remove quotes or spaces around the key
- Verify the key format:
  - Gemini: No specific prefix
  - OpenAI: Starts with `sk-`
  - OpenRouter: Starts with `sk-or-`

### AI Assistant shows "unconfigured" with invalid model message

**Solution:**
- Verify the model ID is correct for your provider
- Check official documentation for current model names
- Ensure the model is accessible with your API key (some models require specific account access)

### Rate limit errors (HTTP 429)

**Solution:**
- Wait for the rate limit to reset (minute or daily)
- Increase limits in `.env` if appropriate for your use case
- Check your provider's quota in their dashboard

### Timeout errors

**Solution:**
- Increase `AI_TIMEOUT_SECONDS` in `.env`
- Check network connectivity to the provider
- Verify the provider is not experiencing an outage

### Import errors about missing SDK

**Solution:**
```bash
pip install -r requirements.txt
```

This installs both `google-genai` and `openai` packages.

### Quota exhausted errors

**Solution:**
- Check your provider's billing/quota dashboard
- Upgrade your plan if needed
- Monitor usage in your provider's console

## Features

### Chat Assistant

- Maintains conversation context (configurable history length)
- Provides government exam guidance
- Never invents official notifications or deadlines
- Safe error handling with user-friendly messages
- Rate limiting per user (per-minute and daily)

### Job Search Assistant

- Interprets natural language queries
- Extracts structured filters (organization, qualification, location, category)
- Falls back to rule-based extraction if AI is unavailable
- Searches verified database records only
- Never fabricates job postings

### Security

- API keys never logged or exposed
- CSRF protection enforced
- Authentication required for all endpoints
- Rate limiting prevents abuse
- Input validation and sanitization
- Provider-specific error handling

## Limitations

- AI responses are generated by the selected provider and may occasionally be incorrect
- The assistant does not have real-time access to official government websites
- Always verify critical information from official sources
- Rate limits are enforced per user to prevent abuse
- Some providers may have model access restrictions based on account type

## Support

For provider-specific issues:
- Gemini: https://ai.google.dev/support
- OpenAI: https://help.openai.com/
- OpenRouter: https://openrouter.ai/support

For Django/project issues, check the Django logs for detailed error messages.
