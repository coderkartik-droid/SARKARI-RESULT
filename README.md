# Sarkari Result · AI Assistant & Smart Jobs Search

A modern government jobs portal featuring a secure, privacy-focused AI Assistant powered by Gemini and a verified database jobs search engine.

---

## 🚀 Quick Setup Guide (Windows PowerShell)

Follow these simple steps in your VS Code terminal (PowerShell) to configure and run the project.

### 1. Where the `.env` file is located

The configuration file is located directly in your project root folder:

```text
C:\Users\GIGABYTE i9\SARKARI RESULT\.env
```

Alongside `manage.py`, `requirements.txt`, and `.gitignore`.

---

### 2. How to create a Gemini API key

1. Open **[Google AI Studio](https://aistudio.google.com/)**.
2. Create a Gemini API key and copy it.
3. Paste it only into the private project-root `.env` file. Never send it in chat, commit it, or put it in HTML/JavaScript.

---

### 3. Configure the private `.env` file

Set the Gemini variables in `.env`:

```dotenv
GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE"
GEMINI_MODEL="gemini-2.5-flash"
AI_PROVIDER="gemini"
AI_ENABLED="True"
```

Replace the placeholder with your key locally. AI is enabled by this configuration, but provider calls will not work until you enter a valid Gemini API key.

For local development, `manage.py` uses `config.settings.development`, which creates a temporary random Django secret if `DJANGO_SECRET_KEY` is not set and allows localhost. For production, set `DJANGO_SETTINGS_MODULE=config.settings.production` and configure a unique `DJANGO_SECRET_KEY` of at least 50 characters, a comma-separated `DJANGO_ALLOWED_HOSTS` list (without `*`), and the database variables shown in `.env.example`. Set `CSRF_TRUSTED_ORIGINS` to the full HTTPS origins that need cross-origin CSRF trust; it may be left unset when the site only posts to its own origin. Never use the development settings module in production.

CMS image uploads accept PNG, JPG/JPEG, and WebP image data. The default maximum upload size is 5 MiB; set `CMS_MAX_IMAGE_SIZE` to a positive number of bytes to change it.

> ⚠️ **Important:**
> - Quotation marks are optional in `.env` values; do not include stray quotes inside a credential.
> - Never paste your key into a message or anywhere else (not in HTML, JavaScript, or Git).
> - `.env` is ignored by Git; `.env.example` contains only a safe placeholder.

---

### 4. AI enablement

The sample configuration enables AI with `AI_ENABLED="True"`. Replace the Gemini API key placeholder before using the assistant. To disable AI, set:

```dotenv
AI_ENABLED="False"
```

Keep the configured Gemini model in `GEMINI_MODEL`. Restart Django after changing `.env`.

---

### 5. How to install dependencies

In your VS Code terminal (PowerShell), run:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

---

### 6. How to run database migrations

Make sure database tables for jobs and accounts are up to date:

```powershell
.\.venv\Scripts\python manage.py migrate
```

---

### 7. How to start the Django server

Start the local development server:

```powershell
.\.venv\Scripts\python manage.py runserver
```

Now open your browser and navigate to:
**[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

### 8. Manage website content

Use an existing Django staff or superuser account; the management area does not have separate credentials and has no public-site navigation link.

1. Open **[http://127.0.0.1:8000/site-management/login/](http://127.0.0.1:8000/site-management/login/)**.
2. Sign in with the existing Django staff or superuser username and password.
3. Manage site identity and homepage text in **General settings**. Use the dashboard to create and reorder navigation, homepage content, announcement, hero-button, and footer sections and their links/buttons. Use a parent item to add a dropdown entry.
4. Public text is rendered as escaped text, and destinations accept only local paths or HTTP/HTTPS URLs.

The initial CMS migration seeds editable defaults matching the existing homepage. Apply pending migrations after updating the project:

```powershell
.\.venv\Scripts\python manage.py migrate
```

---

### 9. How to test the chatbot safely

1. On the homepage, look at the bottom-right corner.
2. Click the floating **"AI Assistant"** button with the violet & pink gradient.
3. The chat panel will open. You can:
   - Click a suggestion chip (e.g. *"What is the SSC CGL eligibility criteria?"*).
   - Switch to the **"Search Verified Jobs"** tab to search vacancies stored in your database (e.g. *"Railway"* or *"10th pass"*).
4. Run automated mock tests anytime (these **never consume your API quota**):

```powershell
.\.venv\Scripts\python manage.py test
```

---

### 10. How to confirm the key is not exposed

- **Git Protection:** `.env` is already declared in `.gitignore`. Even when you use Git or push to GitHub, your private `.env` file will never be committed.
- **Frontend & Browser Protection:** The frontend only speaks to `/api/ai/chat/` and `/api/ai/jobs/` using Django views with CSRF tokens. Your Gemini API key is stored and used solely on the backend inside Python. Open Browser Developer Tools (`F12`) -> Network tab or inspect source (`Ctrl + U`): your key is never transmitted or revealed.
- **Safe Server-Side Validation:** If the key is missing or set to the placeholder, the server detects it and returns a helpful setup hint without crashing or sending any external request.

---

### 11. Google OAuth Setup Guide

To enable Google sign-in:

1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create a new project or select an existing one.
3. Navigate to **APIs & Services** > **OAuth consent screen**:
   - Choose **External** user type and fill in the required app info (e.g., App name: `Niyukti`, Support email).
   - Add scopes: `.../auth/userinfo.email` and `.../auth/userinfo.profile`.
   - Add your test Google accounts under **Test users**.
4. Navigate to **APIs & Services** > **Credentials**:
   - Click **Create Credentials** > **OAuth client ID**.
   - Select **Web application** as Application type.
   - Under **Authorized JavaScript origins**, add:
     - `http://localhost:8000`
     - `http://127.0.0.1:8000`
   - Under **Authorized redirect URIs**, add BOTH of these URLs:
     - `http://localhost:8000/accounts/google/login/callback/`
     - `http://127.0.0.1:8000/accounts/google/login/callback/`
5. Copy your **Client ID** and **Client Secret**, and paste them into your private `.env` file:

```dotenv
GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="your-client-secret"
```

**CRITICAL:** The redirect URIs MUST be configured correctly in Google Cloud Console. If you see a white screen at `/gsi/transform`, it means the redirect URIs are missing or incorrect. Add both `localhost:8000` and `127.0.0.1:8000` variants to avoid this issue.

6. Restart your Django development server. Google sign-in is now live.

> 🔒 **Security Notice:**
> - Existing accounts with matching email addresses are linked safely **only** when Google asserts that the email address is verified.
> - Third-party unverified emails are never allowed to silently take over an existing user account.
> - If credentials are not configured, clicking the Google button provides a clear instruction message rather than failing.

---

### 12. Password Reset & Email Configuration

Django's secure password reset workflow sends one-time cryptographic reset links to registered users.

#### Gmail SMTP

```dotenv
EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST="smtp.gmail.com"
EMAIL_PORT="587"
EMAIL_HOST_USER="your-gmail-address@gmail.com"
EMAIL_HOST_PASSWORD="your-16-character-google-app-password"
EMAIL_USE_TLS="True"
EMAIL_USE_SSL="False"
EMAIL_TIMEOUT="10"
DEFAULT_FROM_EMAIL="your-gmail-address@gmail.com"
PASSWORD_RESET_TIMEOUT="86400"
```

Replace the placeholders in your private `.env`. For Gmail, enable 2-Step Verification and create a Google App Password; use that 16-character password, not your normal Gmail password. Restart Django after changing `.env`. With the console backend, messages only appear in the server terminal and are not delivered to inboxes.

For another provider, use its SMTP host, port, and TLS/SSL requirements instead. Do not enable both `EMAIL_USE_TLS` and `EMAIL_USE_SSL`.

> 🛡️ **Privacy & Security:**
> - Requesting a reset for an unregistered email returns the exact same success response, preventing account enumeration.
> - Password reset tokens are single-use, time-limited, and expire after 24 hours (or `PASSWORD_RESET_TIMEOUT`).
> - New passwords are validated by `PasswordPolicyValidator` (8+ characters, at least one number).

---

## 📁 Architecture Overview

- **`site_management/`**: Staff-only website CMS with database-backed global settings, ordered homepage/navigation/footer content, nested menu links, validated URLs, and CSRF-protected CRUD forms. The login reuses Django authentication and only permits staff/superusers.
- **`ai_assistant/`**: Dedicated Django app containing:
  - `services/gemini_provider.py`: Gemini API adapter with placeholder detection, bounded responses, and sanitized errors.
  - `services/base.py`: Shared provider interface and timeout exception.
  - `services/job_search.py`: Natural language query interpreter & parameterized Django ORM search (never executes raw SQL, never hallucinates jobs).
  - `views.py`: Throttled, CSRF-protected JSON endpoints (`/api/ai/chat/`, `/api/ai/jobs/`, `/api/ai/status/`).
  - `templates/` & `static/`: Accessible, mobile-responsive chat widget in charcoal/navy, violet, and pink theme.
- **`jobs/`**: Dedicated Django app for verified government jobs:
  - `models.py`: `Job` model with organization, qualifications, application dates, official URLs, verification badges, and publication status.
  - `admin.py`: Django Admin interface for managing job records.
- **`accounts/`**: Existing user authentication, login/signup, dashboard, and home view (fully preserved).
