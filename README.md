# Linux Daily: Instagram auto-poster

30 days · 150 commands · 210 image posts · fully automatic.

## Daily timetable (IST)

| Time  | Post |
|-------|------|
| 08:00 | Answers to yesterday's quiz (from Day 2) |
| 09:00 | Lesson 1 |
| 11:00 | Lesson 2 |
| 13:00 | Lesson 3 |
| 16:00 | Lesson 4 |
| 18:00 | Lesson 5 |
| 20:00 | Quiz on today's 5 commands |

Change times in `config.json` → `slots`, then run `python3 scripts/render.py`.

## What's in here

```
posts/                     210 ready images (1080x1350 JPEG)
content/days_*.json        all lessons + quizzes (edit text here)
content/captions.json      captions + hashtags (generated)
content/schedule.json      what posts when (generated)
config.json                handle, tagline, start date, times, GitHub info
scripts/render.py          rebuilds images, captions and schedule
scripts/post.py            posts whatever is due
state.json                 what's already posted (the bot updates it)
.github/workflows/         runs post.py every hour, 8 AM to 9 PM IST
```

---

## Setup: step by step (about 30 minutes, one time)

### Step 1: Instagram account
1. Create the new Instagram account for the page.
2. Profile → ☰ → Settings → **Account type and tools** → **Switch to professional account** → **Creator**.

### Step 2: Get your Instagram API token (free)
1. Go to **developers.facebook.com** and log in → **My Apps** → **Create App**.
2. Choose the use case for managing messaging and content on Instagram, then finish creating the app.
3. In the app dashboard, open **Instagram → API setup with Instagram login**.
4. Under **Generate access tokens**, click **Add account** and log in with your Instagram page.
5. Click **Generate token** and copy it somewhere safe. This is your **IG_ACCESS_TOKEN**.
6. Copy the numeric ID shown next to your account. This is your **IG_USER_ID**.

> Posting to your own account works while the app is in development mode.
> No App Review is needed for that.

### Step 3: Edit config.json (on your PC)
```json
"handle": "@your_insta_handle",
"github_user": "your-github-username",
"github_repo": "linux-daily",
"start_date": "2026-11-10"        <- the day you want Day 1 to go live
```
Then re-render so your handle appears on every image:
```
pip install pillow
python3 scripts/render.py
python3 scripts/post.py --list     # check the timetable
```

### Step 4: Put it on GitHub
1. github.com → **New repository** → name it `linux-daily` → **Public** → Create.
2. Upload this folder:
   ```
   cd linux-daily
   git init && git add . && git commit -m "Linux Daily"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/linux-daily.git
   git push -u origin main
   ```
3. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `IG_USER_ID`: from Step 2
   - `IG_ACCESS_TOKEN`: from Step 2
4. Repo → **Settings → Actions → General → Workflow permissions** → **Read and write** → Save.
5. Repo → **Actions** tab → enable workflows if asked.

### Step 5: Test
1. **Actions → Instagram auto-post → Run workflow** with **Dry run ✔**.
   The log should say what's due (or "Nothing due now. Next: ...").
2. Optional real test on a spare post: on your PC run
   `IG_USER_ID=... IG_ACCESS_TOKEN=... python3 scripts/post.py --id day01-1-pwd`
   (then delete it from Instagram and keep `state.json` as `{"history": []}`).

That's it. From `start_date`, everything posts by itself. ✅

---

## Maintenance

- **Refresh the token every ~50 days** (tokens last 60). Run this and paste the result into the
  `IG_ACCESS_TOKEN` secret:
  ```
  curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=YOUR_TOKEN"
  ```
- **A post failed?** Actions tab → open the red run → read the error. The next hourly run retries.
- **Missed runs** catch up automatically, one post per hour.
- **Pause:** Actions tab → the workflow → ⋯ → Disable workflow.
- **Edit a lesson:** change `content/days_*.json`, run `render.py`, push.

## Adding the next 30 days
Add `content/days_31_35.json` and so on (same format), set `series_length` to 60 in `config.json`,
run `render.py`, push.
