"""
Main entry point for the Nellis Auction Monitor application.
"""

import logging
import logging.handlers
import signal
import sys
import asyncio
import os
import time
from pathlib import Path
import yaml

from app.scraper import AuctionScraper
from app.matcher import KeywordMatcher
from app.notifier import EmailNotifier
from app.scheduler import AuctionScheduler


# Setup logging
def setup_logging(log_dir: str, log_level: str = "INFO"):
    """Setup logging configuration."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    log_file = log_path / "auction_monitor.log"
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10485760,  # 10 MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)


# Load configuration
def load_config(config_file: str = "config/config.yaml"):
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        raise


# Load keywords
def load_keywords(keywords_file: str = "config/keywords.yaml"):
    """Load keywords from YAML file."""
    try:
        with open(keywords_file, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('keywords', [])
    except Exception as e:
        print(f"Error loading keywords: {e}")
        raise


# Main scraping task
async def scrape_and_notify(
    scraper: AuctionScraper,
    matcher: KeywordMatcher,
    notifier: EmailNotifier,
    min_rating: int,
    max_rating: int,
    min_price: float,
    max_pages: int,
    logger
):
    """
    Execute the main scraping and notification task.
    """
    try:
        logger.info("=" * 50)
        logger.info("Starting auction scrape job")
        
        # Scrape listings
        logger.info("Scraping Delran NJ listings...")
        if scraper.categories:
            logger.info(f"Filtering by categories: {', '.join(scraper.categories)}")
        else:
            logger.info("No category filtering applied (scraping all categories)")
        listings = await scraper.scrape_listings(max_pages=max_pages)
        
        # Filter by rating and price
        filtered_listings = []
        for listing in listings:
            rating = listing.get('rating', 0)
            est_retail_text = listing.get('estimated_retail', 'N/A')
            
            # Parse estimated retail price (handles numeric from Remix API or "$N" strings)
            try:
                if isinstance(est_retail_text, (int, float)):
                    price_value = float(est_retail_text)
                elif est_retail_text and est_retail_text != 'N/A':
                    price_value = float(str(est_retail_text).lstrip('$').replace(',', ''))
                else:
                    price_value = 0.0
            except (ValueError, AttributeError):
                price_value = 0.0
            
            # Apply filters
            if min_rating <= rating <= max_rating and price_value >= min_price:
                filtered_listings.append(listing)
        
        logger.info(f"Filtered to {len(filtered_listings)} listings with {min_rating}-{max_rating} star rating and >= ${min_price}")

        # Match keywords
        matched_listings = matcher.find_matches(filtered_listings)
        
        # Send notification if matches found
        if matched_listings:
            logger.info(f"Sending notification with {len(matched_listings)} matched listings")
            notifier.send_notification(matched_listings)
        else:
            logger.info("No keyword matches found, no notification sent")
        
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"Error during scrape job: {e}", exc_info=True)


def main():
    """Main application entry point."""
    
    # Setup logging
    logger = setup_logging(
        log_dir="logs",
        log_level=os.getenv("LOG_LEVEL", "INFO")
    )
    
    logger.info("Starting Nellis Auction Monitor")
    
    try:
        # Load configuration
        config = load_config()
        keywords = load_keywords()
        
        # Extract config values
        scraper_config = config.get('scraper', {})
        scheduler_config = config.get('scheduler', {})
        email_config = config.get('email', {})
        filters_config = config.get('filters', {})
        
        # Substitute environment variables in email config
        email_config['fromEmail'] = os.getenv(
            'AUCTION_EMAIL_ADDRESS',
            email_config.get('fromEmail', '')
        )
        email_config['password'] = os.getenv(
            'AUCTION_EMAIL_PASSWORD',
            email_config.get('password', '')
        )
        email_config['recipientEmail'] = os.getenv(
            'AUCTION_EMAIL_ADDRESS',
            email_config.get('recipientEmail', email_config.get('fromEmail', ''))
        )
        
        # Validate email configuration
        if not email_config.get('fromEmail') or not email_config.get('password'):
            logger.warning("Email credentials not configured. Notifications will be disabled.")
            logger.info("Set AUCTION_EMAIL_ADDRESS and AUCTION_EMAIL_PASSWORD environment variables")
        
        # Initialize components
        logger.info("Initializing components...")
        
        scraper = AuctionScraper(
            base_url=scraper_config.get('baseUrl'),
            request_delay=scraper_config.get('requestDelaySeconds', 7),
            page_timeout=scraper_config.get('pageLoadTimeoutSeconds', 30),
            headless=scraper_config.get('headless', True),
            categories=scraper_config.get('categories'),
            location_code=scraper_config.get('locationCode'),
            proxy_url=os.getenv('SOCKS5_PROXY_URL')
        )
        
        # Get max pages from config
        max_pages = scraper_config.get('maxPages', 5)

        matcher = KeywordMatcher(keywords)
        
        notifier = EmailNotifier(
            smtp_server=email_config.get('smtpServer'),
            smtp_port=email_config.get('smtpPort', 587),
            from_email=email_config.get('fromEmail'),
            password=email_config.get('password'),
            recipient_email=email_config.get('recipientEmail'),
            use_tls=email_config.get('useTLS', True),
            subject_template=email_config.get('subjectTemplate')
        )
        
        scheduler = AuctionScheduler(
            timezone=scheduler_config.get('timezone', 'America/New_York')
        )
        
        # Define the task
        async def scheduled_task():
            await scrape_and_notify(
                scraper=scraper,
                matcher=matcher,
                notifier=notifier,
                min_rating=filters_config.get('minStarRating', 4),
                max_rating=filters_config.get('maxStarRating', 5),
                min_price=filters_config.get('minEstimatedRetailPrice', 50),
                max_pages=max_pages,
                logger=logger
            )
        
        # If skipScheduleInDebug is enabled, run once immediately and exit
        skip_schedule_in_debug = scheduler_config.get('skipScheduleInDebug', False)

        # APScheduler's BackgroundScheduler runs jobs in threads and cannot await
        # coroutines, so wrap the async task in a sync function.
        def run_task():
            asyncio.run(scheduled_task())

        if skip_schedule_in_debug:
            logger.info("skipScheduleInDebug enabled: running scrape job once immediately, then scheduling normally")
            run_task()

        # Schedule the daily task
        scheduler.schedule_daily_task(
            run_time=scheduler_config.get('runTime', '09:00'),
            task_func=run_task
        )

        # Start scheduler
        scheduler.start()
        logger.info("Scheduler is now running. Press Ctrl+C to stop.")
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal")
            scheduler.stop()
            logger.info("Application stopped")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Keep running
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                signal_handler(None, None)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
