# Google Sign-In White Screen Fix

## Root Cause

The `/gsi/transform` white screen occurs due to **misconfigured Google OAuth redirect URIs** in Google Cloud Console.

### Technical Explanation

The project implements **two Google Sign-In methods**:

1. **Modern GIS (Google Identity Services)** - JavaScript button
   - Loads Google's GIS library from `https://accounts.google.com/gsi/client`
   - Renders the official "Continue with Google" button
   - On successful sign-in, receives a JWT credential
   - POSTs the JWT to `/accounts/google/verify/` for server-side verification
   - This is the preferred method when properly configured

2. **Classic OAuth Redirect** - django-allauth flow
   - Traditional OAuth 2.0 redirect flow
   - Redirects user to Google's OAuth consent screen
   - Google redirects back to `/accounts/google/login/callback/`
   - django-allauth completes the authentication

### Why the White Screen Occurs

When the GIS button fails to initialize (due to missing or invalid `GOOGLE_CLIENT_ID`, or unauthorized JavaScript origin), the system falls back to the classic OAuth redirect form. This form POSTs to `/accounts/google/login/`, which triggers django-allauth's OAuth flow.

If the **Authorized Redirect URIs** in Google Cloud Console are missing or incorrect:
- Google cannot redirect back to your callback URL
- Instead, Google redirects to its internal endpoint `/gsi/transform`
- This endpoint displays a blank white screen

## The Fix

### 1. Backend Error Handling (accounts/views.py)

Added exception handling to `google_login_view` to catch OAuth failures and provide helpful error messages:

```python
def google_login_view(request):
    if request.user.is_authenticated:
        return redirect(_login_redirect_url(request, request.user))

    if not is_google_oauth_configured():
        messages.error(
            request,
            "Google sign-in is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env. "
            "Also ensure authorized redirect URIs are configured in Google Cloud Console.",
        )
        return redirect("accounts:login")

    from allauth.socialaccount.providers.google.views import oauth2_login

    try:
        return oauth2_login(request)
    except Exception as exc:
        logger.error("Google OAuth login failed: %s", exc, exc_info=True)
        messages.error(
            request,
            "Google sign-in failed. This usually means the redirect URI is not configured "
            "in Google Cloud Console. Ensure the following URIs are authorized: "
            "http://localhost:8000/accounts/google/login/callback/ and "
            "http://127.0.0.1:8000/accounts/google/login/callback/"
        )
        return redirect("accounts:login")
```

### 2. Frontend Error Handling (accounts/static/accounts/google_auth.js)

Improved the boot function to show a clear error message when Google Client ID is not configured:

```javascript
if (!CLIENT_ID || CLIENT_ID === PLACEHOLDER) {
  console.warn(
    "[Google Auth] Client ID is not configured. Set GOOGLE_CLIENT_ID in .env " +
    "(obtain it from Google Cloud Console > APIs & Services > Credentials). " +
    "Falling back to the classic OAuth redirect button."
  );
  setStatus("Google sign-in requires configuration. Use the button below.", "error");
  setClassicFallbackVisible(true);
  return;
}
```

### 3. Documentation Updates

Updated `README.md` and `.env.example` with clear instructions about configuring redirect URIs in Google Cloud Console.

## Required Google Cloud Console Configuration

To fix the white screen, you MUST configure the following in Google Cloud Console:

### Step 1: Create OAuth Client ID

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project or create a new one
3. Navigate to **APIs & Services** > **Credentials**
4. Click **Create Credentials** > **OAuth client ID**
5. Select **Web application**

### Step 2: Configure Authorized JavaScript Origins

Add both of these origins:
- `http://localhost:8000`
- `http://127.0.0.1:8000`

### Step 3: Configure Authorized Redirect URIs (CRITICAL)

Add BOTH of these redirect URIs:
- `http://localhost:8000/accounts/google/login/callback/`
- `http://127.0.0.1:8000/accounts/google/login/callback/`

**⚠️ IMPORTANT:** Both variants (localhost and 127.0.0.1) must be added to avoid the white screen, as Django may be accessed via either hostname.

### Step 4: Copy Credentials

Copy the **Client ID** and **Client Secret** and add them to your `.env` file:

```dotenv
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### Step 5: Restart Server

Restart your Django development server for the changes to take effect.

## Production Configuration

For production deployment:

1. Add your production domain to **Authorized JavaScript Origins**:
   - `https://yourdomain.com`

2. Add your production callback to **Authorized Redirect URIs**:
   - `https://yourdomain.com/accounts/google/login/callback/`

3. Update `CSRF_TRUSTED_ORIGINS` in your production environment:
   ```dotenv
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com
   ```

4. Update `DJANGO_ALLOWED_HOSTS`:
   ```dotenv
   DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   ```

## Verification

After applying the fix:

1. Restart the Django development server
2. Navigate to the login page
3. Click "Continue with Google"
4. You should see either:
   - The GIS button if Client ID is configured and origins are authorized
   - A clear error message if configuration is missing
   - A successful OAuth redirect if the fallback is used and redirect URIs are correct

The white screen at `/gsi/transform` should no longer occur.

## Files Changed

1. `accounts/views.py` - Added exception handling and logging to `google_login_view`
2. `accounts/static/accounts/google_auth.js` - Improved error message when Client ID not configured
3. `README.md` - Updated Google OAuth setup guide with redirect URI warnings
4. `.env.example` - Added critical warning about redirect URI configuration

## Summary

The root cause was missing or incorrect redirect URIs in Google Cloud Console. The fix provides:
- Better error messages when configuration is missing
- Exception handling to catch OAuth failures
- Clear documentation of required Google Cloud Console setup
- Guidance for both development and production environments
