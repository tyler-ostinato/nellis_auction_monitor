# Nellis Auction Monitor

A Python application that monitors the Nellis Auction website (Delran, NJ location) for listings matching your desired keywords and sends email notifications. Runs daily via scheduled task and can be containerized with Docker/Docker Compose for easy deployment.

## Features

- 🔍 **Automated Scraping**: Monitors Delran NJ warehouse daily at your specified time
- ⭐ **Smart Filtering**: Only shows 4-5 star rated items to focus on quality listings
- 🎯 **Keyword Matching**: Customizable keywords to filter listings of interest
- 📧 **Email Notifications**: Finds matches and sends them directly to your inbox
- 🐳 **Docker Ready**: Fully containerized with Docker Compose
- 🔐 **VPN Support**: Route through NordVPN container to protect your IP
- 📊 **Duplicate Prevention**: Tracks seen listings to avoid duplicate notifications
- 🔄 **Rate Limited**: Conservative 5-10 second delays between requests to avoid detection

## Prerequisites

- Docker & Docker Compose (for containerized deployment)
- OR Python 3.11+ (for local development)
- Gmail/SMTP account for email notifications
- (Optional) NordVPN subscription for VPN routing

## Quick Start - Docker Compose

### 1. Configure Environment Variables

Create a `.env` file in the project root:

```bash
NORD_PRIVATE_KEY=your_nordvpn_private_key_here
AUCTION_EMAIL_ADDRESS=your-email@gmail.com
AUCTION_EMAIL_PASSWORD=your-app-password
```

**For Gmail:**
- Use an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password)
- Enable [Less Secure App Access](https://myaccount.google.com/lesssecureapps) if using regular password

### 2. Configure Keywords

Edit `config/keywords.yaml` and add the items you're interested in:

```yaml
keywords:
  - laptop
  - graphics card
  - solid state drive
  - vintage collectible
  - tool set
```

### 3. Configure Scrape Schedule

Edit `config/config.yaml` to set when the scraper runs daily:

```yaml
scheduler:
  runTime: "09:00"  # 24-hour format (e.g., 09:00 = 9 AM)
  timezone: "America/New_York"
```

### 4. Build and Run

```bash
# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f auction-monitor

# Stop the service
docker-compose down
```

## Local Development Setup

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

```bash
# Create .env file with credentials
AUCTION_EMAIL_ADDRESS=your-email@gmail.com
AUCTION_EMAIL_PASSWORD=your-app-password
```

### 3. Run Locally

```bash
python -m app.main
```

The scheduler will start and run at your configured time each day.

## Configuration Files

### `config/config.yaml`

Main configuration file:

```yaml
scraper:
  baseUrl: "https://nellisauction.com/search?Location+Name=Delran"
  requestDelaySeconds: 7          # Delay between requests (5-10 recommended)
  pageLoadTimeoutSeconds: 30      # Page load timeout
  headless: true                  # Use headless browser mode

scheduler:
  runTime: "09:00"               # Daily run time (HH:MM, 24-hour)
  timezone: "America/New_York"   # Timezone

email:
  smtpServer: "smtp.gmail.com"
  smtpPort: 587
  useTLS: true
  # credentials from env vars:
  # AUCTION_EMAIL_ADDRESS, AUCTION_EMAIL_PASSWORD

filters:
  minStarRating: 4               # Minimum star rating
  maxStarRating: 5               # Maximum star rating

logging:
  level: "INFO"                  # Log level (DEBUG, INFO, WARNING, ERROR)
  logDir: "logs"
  maxLogSizeBytes: 10485760      # 10 MB

data:
  seenListingsFile: "data/seen_listings.json"
```

### `config/keywords.yaml`

Customize keywords for item matching:

```yaml
keywords:
  - laptop
  - graphics card
  - server equipment
  - hard drive
  - monitor
  - networking equipment
```

## Application Architecture

### Modules

- **`scraper.py`**: Fetches listings from Nellis Auction using Playwright
- **`tracker.py`**: Maintains JSON file of seen listings to prevent duplicates
- **`matcher.py`**: Matches listings against configured keywords
- **`notifier.py`**: Sends formatted HTML email notifications
- **`scheduler.py`**: Manages APScheduler for daily task execution
- **`main.py`**: Main entry point and application orchestration

### Workflow

1. **Scraper** fetches all Delran NJ listings
2. **Ratings Filter** keeps only 4-5 star items
3. **Tracker** identifies new listings (not seen before)
4. **Matcher** filters for keyword matches
5. **Notifier** sends email with matched listings
6. **Tracker** saves seen listings for next run

## Logging

Logs are saved to `logs/auction_monitor.log` with rotation after 10 MB.

Output includes:
- Scraping progress and item counts
- Keyword matches
- Email sending status
- Any errors or warnings

View logs with Docker:

```bash
docker-compose logs -f auction-monitor
```

## VPN Routing

The Docker Compose setup includes NordVPN integration:

1. Ensure you have NordVPN credentials
2. Set `NORD_PRIVATE_KEY` in your `.env` file
3. The `auction-monitor` service automatically routes through the VPN container
4. Check logs to confirm IP is routed through VPN

## Troubleshooting

### Email not sending
- Verify `AUCTION_EMAIL_ADDRESS` and `AUCTION_EMAIL_PASSWORD` are set
- For Gmail: Use an [App Password](https://support.google.com/accounts/answer/185833)
- Check logs for SMTP connection errors

### No listings found
- Verify Delran NJ location has active auctions
- Check if website structure has changed
- Search manually at https://nellisauction.com/search?Location+Name=Delran

### Playwright issues
- Run `playwright install chromium` in local development
- Docker automatically installs browsers

### Docker compose build fails
- Ensure Docker daemon is running
- Try: `docker system prune` to clean up unused resources

## Legal Notice

This tool is for personal use to monitor auction listings more efficiently. The Nellis Auction website's Terms of Service prohibit automated scraping without written permission. This tool uses conservative rate limiting (once daily, 5-10 second delays) and respects robots.txt allowances for product pages. Use at your own risk and respect the website's terms of service.

## Development

### Running Tests

```bash
# (Tests to be added)
pytest tests/
```

### Code Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py           # Entry point
│   ├── scraper.py        # Web scraping
│   ├── tracker.py        # Seen listings
│   ├── matcher.py        # Keyword matching
│   ├── notifier.py       # Email sending
│   └── scheduler.py      # Task scheduling
├── config/
│   ├── config.yaml       # Main config
│   └── keywords.yaml     # Keywords
├── data/
│   └── seen_listings.json # Tracking
├── logs/
│   └── auction_monitor.log
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Future Enhancements

- [ ] Add SMS notifications
- [ ] Discord/Slack webhook support
- [ ] Web dashboard for configuration
- [ ] Database persistence for listings
- [ ] Multiple location support
- [ ] Price alert thresholds
- [ ] Item image inline in emails
- [ ] API endpoint for status checks

## License

Personal use only.

## Support

For issues or questions about setup, check the logs and verify:
1. Network connectivity (especially with VPN)
2. Email credentials
3. Nellis Auction website accessibility
4. Keyword relevance to available items
