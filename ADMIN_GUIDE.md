# Sarkari Result Administration Guide

This guide describes the current Django admin and the custom site-management
workspace. The site has two separate staff interfaces: Django Admin for records
such as jobs and comments, and the custom management workspace for the public
site's CMS content.

## Access and sign-in

Start the local development server from the project root:

```powershell
python manage.py runserver
```

The public site is at `http://127.0.0.1:8000/`.

| Interface | URL | Who can sign in |
| --- | --- | --- |
| Custom site management | `/site-management/login/` | Existing Django staff users and superusers |
| Django Admin | `/admin/` | Users with Django admin/staff permissions |
| Public account login | `/accounts/login/` | Registered users |

The custom management login uses the existing Django account; it has no
separate password store. Do not share administrator credentials or add passwords
to source files. New users should be created through the approved account
provisioning process or Django Admin.

## Custom site-management workspace

The dashboard at `/site-management/` is the entry point. Its **Website content
areas** cards open the editor for each area. Section and item forms preserve
existing records and provide field-level errors. Changing a section slug after
publishing can break existing links to that section.

| Management screen | What it controls | Public effect |
| --- | --- | --- |
| **General settings** — `/site-management/settings/` | `WebsiteSettingsForm` edits the site name, tagline, logo text/URL, favicon URL, homepage hero copy and notice, editorial note, and footer description/contact/copyright/disclaimer. | Shared header/footer branding and homepage copy. It does not change routes or upload a logo file; logo fields accept a URL. |
| **Navigation** — `/site-management/content/navigation/` | `ContentSectionForm` and `ContentItemForm` manage CMS navigation sections, links, ordering, and nested dropdown items. | Header navigation, except the permanent Home link, which is supplied by the public template and remains available if CMS navigation is empty. |
| **Homepage** — `/site-management/content/homepage/` | Sections and content items control the homepage's dynamic editorial cards, labels, descriptions, ordering, visibility, and optional links. | Homepage content sections. The Latest Jobs section is intentionally excluded from the homepage; job records are managed separately. |
| **Announcements** — `/site-management/content/announcements/` | Announcement sections and items control notice-bar content and ordering. | The public announcement strip when active and within its publishing schedule. |
| **Homepage buttons** — `/site-management/content/hero_actions/` | Button items control optional hero actions and their destinations. | Buttons near the homepage hero/search area. |
| **Tools landing page** — `/site-management/content/tools/` | The single Tools-area section and its items control the landing-page introduction and cards. | `/tools/`. Individual tool routes and tool behavior are implemented in templates and Python, not configured by this CMS editor. |
| **Footer** — `/site-management/content/footer/` | Footer content sections and items control configured CMS links and their ordering. General footer text is in General settings; informational-page links are generated from configured page routes. | Footer columns and links across public pages. The editor does not change the three-column layout or add a removed column by itself. |
| **Website Pages** — `/site-management/website-pages/` | `WebsitePageCreateForm` selects an available fixed page type; `WebsitePageForm` edits its content, image, optional link, contact details, and publication state. | About Us (`/about-us/`), Contact Us (`/contact-us/`), Privacy Policy (`/privacy-policy/`), Terms and Conditions (`/terms-and-conditions/`), Disclaimer (`/disclaimer/`), and Content Details (`/content-details/`). These are fixed routes, not administrator-created slugs. |
| **Content Links** — `/site-management/links/` | `ContentLinkForm` manages separately scheduled links attached to an existing content item. | Additional links within the parent public content block while active and within its start/end dates. |
| **Social Profiles** — `/site-management/social-profiles/` | `SocialMediaProfileForm` configures platform URL, icon, color, active state, ordering, and header/footer placement. | Social links in the public header and/or footer. Only configure accounts that the site actually owns. |
| **Messages** — `/site-management/messages/` | Staff can review contact submissions and open their detail view. | Private inbox; submissions are not public. Django Admin also lists them under Site Management → Contact submissions. |

### Pages and content sources

- **Home (`/`)** is not a `WebsitePage` record. Its brand and hero copy come
  from General settings; dynamic sections, notices, hero buttons, navigation,
  and footer links come from the corresponding CMS areas. Search results come
  from the existing jobs and CMS query logic.
- **Job listings (`/jobs/`) and job details (`/jobs/details/<id>/`)** come from
  `jobs.Job`, not Website Pages or CMS content.
- **Eligibility checking (`/jobs/check-eligibility/`)** evaluates the age and
  qualification fields on eligible job records.
- **CMS section pages (`/accounts/sections/<slug>/`)** show the active content
  items for the selected homepage-area section.
- The navigation Home item is fixed in the public template. Other CMS
  navigation entries do not replace or duplicate that link.

## Managing jobs and publishing updates

1. Open Django Admin at `/admin/` and choose **Jobs → Government Jobs**. The
   direct changelist URL is `/admin/jobs/job/`.
2. Add or edit a job's organization, category, qualification, location,
   vacancies, age range, cutoff date, application dates, and official URLs.
   Age-relaxation rules are managed inline on the job.
3. Keep a new or incomplete record in **Draft**. Before marking it published
   and verified, check the source and application links against the issuing
   authority. The public verified-jobs listing excludes drafts, unverified
   records, expired records, and records past their application deadline.
4. Mark closed records archived/expired rather than leaving a stale application
   link visible.
5. Use **Site Management → Website Pages** or the relevant content area for
   public copy and CMS notices; do not create a job as a CMS card if it should
   participate in job search, filtering, or eligibility matching.

## Contact submissions and comments

- Contact submissions are available in the custom workspace at
  `/site-management/messages/` and in Django Admin under
  **Site Management → Contact submissions**. Open a submission to read its
  message; the custom workspace displays unread state.
- Community comments are moderated in Django Admin at
  `/admin/comments/comment/`. Use the status filter or inline status editor to
  publish or reject a pending comment. Published comments appear on
  `/comments/`.
- The contact route currently requires an authenticated user to submit a
  message. Contact form submissions are stored as private staff messages.

## Accounts, Google sign-in, and password reset

User accounts are managed in Django Admin under **Accounts** (the configured
custom user model). Signup, login, Google authentication, and password-reset
screens are application workflows, not editable CMS pages. Google OAuth,
email delivery, and password-reset behavior are configured through environment
settings; never place client secrets, SMTP passwords, or reset credentials in
templates, documentation, or Git.

## AI assistant

The assistant UI and API are implemented by the `ai_assistant` app. Its
endpoints are `/api/ai/chat/`, `/api/ai/jobs/`, and `/api/ai/status/`. Provider,
model, and enablement are configured with environment variables such as
`AI_PROVIDER`, `AI_ENABLED`, and `GEMINI_MODEL`. The project does not define a
persistent conversation/transcript model, so there is no conversation inbox to
edit in Django Admin. Daily request usage is tracked separately; do not add
fabricated usage rows because they affect user quotas.

## Demo data command

The development-only seed command adds clearly labelled example content and
does not overwrite existing rows. It refuses to run unless `DEBUG` is enabled
and the explicit `--confirm` option is supplied:

```powershell
python manage.py seed_fake_data --confirm
```

The command seeds 24 fictional job records across six categories, age
relaxations, the fixed information pages, demo homepage sections and notices,
content links, and sample contact submissions. All examples are marked
**DEMO ONLY** and use reserved `example.org` URLs. Job rows remain unverified,
even when their publication status is set to published, so the public verified
jobs selector does not treat them as official listings. A development
announcement/cards can still demonstrate the CMS layout. Review and replace
the placeholder legal-page content before any deployment.

Seeded account creation is optional and requires all of the following
environment variables to be set privately before running the command:

```text
SEED_ADMIN_USERNAME
SEED_ADMIN_EMAIL
SEED_ADMIN_PASSWORD
SEED_TEST_USERNAME
SEED_TEST_EMAIL
SEED_TEST_PASSWORD
```

The command never prints passwords, never changes a password on an existing
account, and never elevates an existing non-superuser. If a test account is not
configured, sample comments are skipped because comments must have a real
author. Do not send passwords in chat, add them to this guide, or commit them
to `.env.example` or source control.

## Common troubleshooting

### Changes do not appear on the public site

1. Confirm the section/item is active, its parent section is active, and any
   `publish_at` / `expires_at` window includes the current time.
2. For jobs, confirm the record is published, verified, not expired, and still
   within its application deadline. Do not mark demo data verified to make it
   appear in the public jobs list.
3. Confirm that you edited the matching route/area. Homepage copy in General
   settings and content cards in the Homepage area are separate controls.
4. Reload the page without the browser cache (`Ctrl+F5`). This project uses a
   local-memory cache for authentication throttling, not a configured
   full-page cache; restarting the development server is not normally needed
   for database edits.
5. If static assets changed during development, restart the server and reload.
   For production static deployment, run `python manage.py collectstatic` as
   part of the deployment process.

### Database or migration errors

Check the active settings and migration state before changing a database:

```powershell
python manage.py showmigrations
python manage.py makemigrations --check
```

Apply reviewed pending migrations with:

```powershell
python manage.py migrate
```

If Django reports multiple migration leaf nodes, inspect the dependency and
operation lists for every conflicting migration before generating a merge.
Only merge branches whose operations can safely coexist; duplicate
`AddField`/`CreateModel` operations need reconciliation rather than an empty
merge. Never delete applied migrations, fake migration state, or reset the
database to suppress a conflict. Back up the development database before any
schema change, and do not run development instructions against production.

### Login or email issues

- Use an existing staff account for `/site-management/login/`; normal
  non-staff accounts cannot access that workspace.
- Confirm the configured email backend and environment variables locally
  without printing secrets. The development default is the console email
  backend, which writes reset mail to the server console instead of delivering
  it to a mailbox.
- After changing environment settings, restart the Django process. Never
  include credentials in error reports.

## Useful maintenance commands

Run these from the directory containing `manage.py`:

```powershell
python manage.py check
python manage.py test
python manage.py showmigrations
python manage.py runserver
```

Tests use an isolated test database. Do not run migrations or reset the
development database merely to make a test pass; investigate migration and
runtime errors separately.
