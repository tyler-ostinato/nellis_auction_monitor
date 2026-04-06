"""
Tracker module for managing seen listings to avoid duplicates.
"""

import json
import logging
from pathlib import Path
from typing import Set, Dict, Any

logger = logging.getLogger(__name__)


class ListingTracker:
    def __init__(self, seen_listings_file: str):
        """
        Initialize the tracker.
        
        Args:
            seen_listings_file: Path to JSON file storing seen listing IDs
        """
        self.seen_file = Path(seen_listings_file)
        self.seen_listings = self._load_seen_listings()
    
    def _load_seen_listings(self) -> Set[str]:
        """
        Load previously seen listing IDs from file.
        
        Returns:
            Set of listing IDs that have been seen before
        """
        try:
            if self.seen_file.exists():
                with open(self.seen_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} previously seen listings")
                    return set(data.get('ids', []))
            else:
                logger.info("No previous listing history found, starting fresh")
                return set()
        except Exception as e:
            logger.error(f"Error loading seen listings: {e}")
            return set()
    
    def save_seen_listings(self) -> None:
        """Save current seen listings to file."""
        try:
            self.seen_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.seen_file, 'w') as f:
                data = {
                    'ids': list(self.seen_listings),
                    'count': len(self.seen_listings)
                }
                json.dump(data, f, indent=2)
                logger.debug(f"Saved {len(self.seen_listings)} seen listings")
        except Exception as e:
            logger.error(f"Error saving seen listings: {e}")
    
    def get_new_listings(self, listings: list) -> list:
        """
        Filter listings to only return new (unseen) ones.
        
        Args:
            listings: List of listing dictionaries
        
        Returns:
            List of new listings that haven't been seen before
        """
        new_listings = []
        
        for listing in listings:
            listing_id = listing.get('id')
            if not listing_id:
                logger.warning(f"Listing missing ID: {listing.get('title')}")
                continue
            
            if listing_id not in self.seen_listings:
                new_listings.append(listing)
                self.seen_listings.add(listing_id)
                logger.debug(f"New listing found: {listing.get('title')}")
            else:
                logger.debug(f"Skipping seen listing: {listing.get('title')}")
        
        logger.info(f"Found {len(new_listings)} new listings out of {len(listings)} total")
        return new_listings
    
    def mark_as_seen(self, listing_id: str) -> None:
        """Mark a specific listing as seen."""
        self.seen_listings.add(listing_id)
    
    def is_seen(self, listing_id: str) -> bool:
        """Check if a listing has been seen before."""
        return listing_id in self.seen_listings
