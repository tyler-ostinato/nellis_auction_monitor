"""
Scheduler module for managing periodic tasks.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Callable

logger = logging.getLogger(__name__)


class AuctionScheduler:
    def __init__(self, timezone: str = "America/New_York"):
        """
        Initialize the scheduler.
        
        Args:
            timezone: Timezone for scheduling
        """
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self.timezone = timezone
    
    def schedule_daily_task(self, run_time: str, task_func: Callable, job_id: str = "daily_scrape") -> None:
        """
        Schedule a task to run daily at specified time.
        
        Args:
            run_time: Time in HH:MM format (24-hour)
            task_func: Callable function to execute
            job_id: Unique job identifier
        """
        try:
            hour, minute = map(int, run_time.split(':'))
            
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )
            
            self.scheduler.add_job(
                task_func,
                trigger=trigger,
                id=job_id,
                name=f"Daily auction scrape at {run_time}",
                replace_existing=True
            )
            
            logger.info(f"Scheduled daily task at {run_time} ({self.timezone})")
            
        except Exception as e:
            logger.error(f"Error scheduling task: {e}")
            raise
    
    def start(self) -> None:
        """Start the scheduler."""
        try:
            self.scheduler.start()
            logger.info("Scheduler started")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        try:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def get_jobs(self):
        """Get information about scheduled jobs."""
        return self.scheduler.get_jobs()
