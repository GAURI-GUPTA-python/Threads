# Threads Post Scheduler

Give it content and a time in a spreadsheet — it posts to your Threads account
automatically, running on your own PC/server via cron.

## How it works

1. You add rows to `posts.csv` (text + when to post it).
2. `threads_scheduler.py` runs every few minutes (via cron), checks for posts
   whose scheduled time has passed and are still marked `pending`, and
   publishes them to Threads.
3. Each row gets marked `posted` (or `error`, with a note) so nothing posts twice.

---

## 1. Get your Threads API credentials

Threads posting requires a Meta Developer app with Threads API access.

1. Go to https://developers.facebook.com/ and log in with the Facebook
   account linked to your Threads account.
2. Create a new app → choose **"Other"** → **"Business"** as the app type.
3. In the app dashboard, add the **"Threads API"** product.
4. Under Threads API settings, generate a **User Token** for your Threads
   account and grant these scopes: `threads_basic`, `threads_content_publish`.
5. Use the [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/)
   or Meta's token exchange endpoint to convert the short-lived token into a
   **long-lived token** (valid ~60 days). You'll need to refresh it before it
   expires — Meta's docs cover the refresh endpoint.
6. Note your **Threads User ID** (shown in the same dashboard section).

Full official reference: https://developers.facebook.com/docs/threads

This is the fiddly part — if you get stuck on any step, paste the error or
screen you're seeing and I can help you troubleshoot it.

## 2. Install

```bash
cd threads-scheduler
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and paste in your `THREADS_USER_ID` and `THREADS_ACCESS_TOKEN`.

## 3. Add posts to the queue

Edit `posts.csv`. Columns:

| Column | Meaning |
|---|---|
| `id` | Any unique number |
| `text` | The post content |
| `image_url` | Optional — a public URL to an image (leave blank for text-only) |
| `scheduled_time` | `YYYY-MM-DD HH:MM` in your machine's local time |
| `status` | Leave as `pending` — the script fills in `posted`/`error` |
| `posted_at` | Filled in automatically |
| `note` | Filled in automatically (success info or error message) |

You can edit this file in Excel/Google Sheets — just export/save as CSV.

## 4. Test it manually

```bash
python3 threads_scheduler.py
```

Check `scheduler.log` to see what happened. Rows with a future
`scheduled_time` are left untouched until it's time.

## 5. Automate with cron (runs every 5 minutes)

```bash
crontab -e
```

Add this line (adjust the path to where you saved the folder):

```
*/5 * * * * cd /full/path/to/threads-scheduler && /usr/bin/python3 threads_scheduler.py >> cron.log 2>&1
```

That's it — from now on, add rows to `posts.csv` whenever you want, and the
script will post them at the right time without you doing anything further.

## Notes & limits

- Threads' API rate-limits posts per user per day — fine for normal personal
  use, but don't schedule dozens per hour.
- Image posts require a **public** image URL (not a local file path) — e.g.
  host it on Imgur, S3, or similar.
- Keep `.env` private — it holds your access token. Don't commit it to a
  public GitHub repo.
- Long-lived tokens expire (~60 days) and need refreshing; Meta's docs
  describe the refresh call, which you could also automate later if wanted.
