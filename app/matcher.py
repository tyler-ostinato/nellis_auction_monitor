"""
Matcher module for matching keywords against listings.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class KeywordMatcher:
    def __init__(self, keywords: List[str]):
        """
        Initialize the matcher.
        
        Args:
            keywords: List of keywords to match against listings
        """
        self.keywords = [kw.lower() for kw in keywords]
        logger.info(f"Initialized matcher with {len(self.keywords)} keywords")
    
    def find_matches(self, listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Find listings that match any of the keywords.
        
        Args:
            listings: List of listing dictionaries
        
        Returns:
            List of listings that match keywords
        """
        matches = []
        
        for listing in listings:
            matched = self._get_matching_keywords(listing)
            if matched:
                listing['matched_keywords'] = matched
                matches.append(listing)
                logger.debug(f"Matched keywords {matched}: {listing.get('title')}")
        
        logger.info(f"Found {len(matches)} keyword matches out of {len(listings)} listings")
        return matches
    
    def _get_matching_keywords(self, listing: Dict[str, Any]) -> List[str]:
        """
        Return all keywords that match a listing's title.

        Returns:
            List of matched keywords (empty if none)
        """
        search_text = (listing.get('title', '') or '').lower()
        return [kw for kw in self.keywords if kw in search_text]
    
    def update_keywords(self, keywords: List[str]) -> None:
        """
        Update the list of keywords.
        
        Args:
            keywords: New list of keywords
        """
        self.keywords = [kw.lower() for kw in keywords]
        logger.info(f"Updated keywords: {len(self.keywords)} keywords now active")
