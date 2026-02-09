# Rent Scraper

A web scraper for monitoring rental listings on Rightmove with Flask dashboard and automated scheduling.

## Features

- 🔍 Search Rightmove for rental properties with customizable filters
- 📊 Web dashboard to view and analyze listings
- ⏰ Automated scheduling with APScheduler
- 📱 Telegram notifications for new listings
- 🤖 AI-powered analysis using Claude (Anthropic)
- ☁️ GitHub Actions support for running in the cloud

## Local Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run the Flask app:**
   ```bash
   python app.py
   ```

4. **Access dashboard:**
   Open http://localhost:5001 in your browser

## GitHub Actions Setup (Run in the Cloud)

To run the scraper automatically in the cloud using GitHub Actions:

### 1. Set up GitHub Secrets

Go to your repository on GitHub:
- Click **Settings** → **Secrets and variables** → **Actions**
- Click **New repository secret** for each of the following:

| Secret Name | Description | Required |
|------------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather | Optional |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Optional |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (if using AI analysis) | Optional |

### 2. Enable GitHub Actions

- Go to **Actions** tab in your repository
- If prompted, enable GitHub Actions
- The workflow will run automatically every hour

### 3. Manual Trigger

You can also run the scraper manually:
- Go to **Actions** tab
- Click **Rent Scraper** workflow
- Click **Run workflow** → **Run workflow**

### 4. View Results

After each run:
- Go to **Actions** tab
- Click on a completed workflow run
- Download **scrape-results** artifact to see the JSON results

## How It Works

### GitHub Actions Workflow

The workflow (`.github/workflows/scrape.yml`) does the following:

1. **Runs on schedule:** Every hour (configurable via cron)
2. **Scrapes Rightmove:** Searches for properties matching your criteria
3. **Saves results:** Stores findings as JSON artifacts
4. **Sends notifications:** (Optional) Sends Telegram alerts for new listings

### Customizing Search Settings

Edit `run_scraper.py` to change search parameters:

```python
settings = {
    "location_display_name": "London",
    "min_price": 1300,
    "max_price": 1750,
    "min_bedrooms": 1,
    "max_bedrooms": 1,
    # ... more settings
}
```

### Changing Schedule

Edit `.github/workflows/scrape.yml` to change when it runs:

```yaml
schedule:
  - cron: '0 * * * *'  # Every hour
  # - cron: '0 9 * * *'  # Daily at 9 AM
  # - cron: '0 */6 * * *'  # Every 6 hours
```

## File Structure

```
rent_scraper/
├── .github/workflows/
│   └── scrape.yml          # GitHub Actions workflow
├── app.py                  # Flask web application
├── scraper.py             # Core scraping logic
├── run_scraper.py         # Standalone script for GitHub Actions
├── database.py            # SQLite database operations
├── analyzer.py            # AI-powered listing analysis
├── notifier.py            # Telegram notifications
├── scheduler.py           # APScheduler setup
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates
└── static/                # CSS and static files
```

## Notes

- GitHub Actions has usage limits (2,000 minutes/month for free tier on private repos)
- Results are stored as artifacts for 30 days
- The scraper respects Rightmove's rate limits with delays between requests
- Make sure not to commit your `.env` file (it's in `.gitignore`)

## License

MIT
