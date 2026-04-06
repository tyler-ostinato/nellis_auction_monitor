"""
Scraper module for fetching Nellis Auction listings from Delran NJ location.
"""

import logging
import time
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


class AuctionScraper:
    def __init__(self, base_url: str, request_delay: int, page_timeout: int, headless: bool = True, categories: List[str] = None, location_code: str = None, proxy_url: str = None):
        """
        Initialize the scraper.

        Args:
            base_url: Base URL for Delran NJ listings
            request_delay: Delay between requests in seconds
            page_timeout: Page load timeout in seconds
            headless: Whether to run browser in headless mode
            categories: List of categories to include (None for all categories)
            location_code: Nellis shopping location code to set before searching
                           (e.g. "phi" for Philadelphia — required for Delran warehouse)
            proxy_url: Optional SOCKS5/HTTP proxy URL (e.g. "socks5://nordvpn-gateway:1080")
        """
        self.base_url = base_url
        self.request_delay = request_delay
        self.page_timeout = page_timeout * 1000  # Convert to milliseconds
        self.headless = headless
        self.categories = [cat.lower() for cat in categories] if categories else None
        self.location_code = location_code
        self.proxy_url = proxy_url
        
    async def scrape_listings(self, max_pages: int = 5) -> List[Dict[str, Any]]:
        """
        Scrape all listings from Delran NJ location, handling pagination.

        Args:
            max_pages: Maximum number of pages to scrape (default 5)

        Returns:
            List of listing dictionaries with title, price, rating, url, etc.
        """
        listings = []

        try:
            async with async_playwright() as p:
                proxy = {"server": self.proxy_url} if self.proxy_url else None
                browser = await p.chromium.launch(headless=self.headless, proxy=proxy)
                page = await browser.new_page()

                # Intercept Remix data API calls (?_data= responses contain clean JSON)
                captured_remix_data = {}

                async def on_response(response):
                    # Remix v1/v2 use ?_data=; Remix v2+Vite uses .data suffix
                    is_remix_data = (
                        '_data=' in response.url
                        or response.url.endswith('.data')
                        or '/.data?' in response.url
                    )
                    if is_remix_data and response.status == 200:
                        try:
                            body = await response.body()
                            data = json.loads(body)
                            captured_remix_data[response.url] = data
                            logger.debug(f"Captured Remix data from: {response.url}")
                        except Exception as e:
                            logger.debug(f"Could not parse Remix response {response.url}: {e}")

                page.on('response', on_response)

                # Set the shopping location session before searching.
                # Nellis requires this so that location-name facet filters work correctly.
                # Without it, the server defaults to Las Vegas and Delran returns 0 results.
                if self.location_code:
                    location_url = f"https://nellisauction.com/change-shopping-location/{self.location_code}"
                    logger.info(f"Setting shopping location: {location_url}")
                    for attempt in range(1, 4):
                        try:
                            await page.goto(location_url, wait_until='load', timeout=self.page_timeout)
                            await page.wait_for_timeout(1000)
                            break
                        except Exception as e:
                            logger.warning(f"Error setting shopping location (attempt {attempt}/3): {e}")
                            if attempt == 3:
                                raise
                            await page.wait_for_timeout(3000 * attempt)

                current_page = 1
                page_index = 0  # 0-based: _p1=s:120,n:{page_index}
                consecutive_empty_pages = 0
                MAX_RETRIES = 3
                MAX_CONSECUTIVE_EMPTY = 3

                while current_page <= max_pages:
                    current_url = self._build_page_url(page_index)
                    captured_remix_data.clear()
                    logger.info(f"Scraping page {current_page}: {current_url}")

                    # Attempt to load the page and extract listings, retrying on empty result
                    page_listings = []
                    meta_data = None
                    load_error = False

                    for attempt in range(1, MAX_RETRIES + 1):
                        captured_remix_data.clear()
                        try:
                            await page.goto(current_url, timeout=self.page_timeout, wait_until='load')
                            await page.wait_for_timeout(2000)  # Wait for any late JS fetches
                        except Exception as e:
                            logger.warning(f"Timeout or error loading page {current_page} (attempt {attempt}): {e}")
                            load_error = True
                            break

                        # Try captured Remix API responses first (most reliable)
                        for url, data in captured_remix_data.items():
                            if isinstance(data, dict):
                                for key in ('products', 'searchResults', 'listings', 'items', 'results'):
                                    if key in data and isinstance(data[key], list):
                                        page_listings = self._parse_remix_listings(data[key])
                                        meta_data = data
                                        logger.info(f"Extracted {len(page_listings)} listings from Remix API response (key: {key})")
                                        break
                            if page_listings:
                                break

                        # Fall back to JS window context evaluation
                        if not page_listings:
                            try:
                                page_listings = await self._extract_listings_from_page(page)
                            except Exception as e:
                                logger.error(f"Error extracting listings from page {current_page}: {e}")
                                page_listings = []

                        if page_listings:
                            break  # Got listings, no need to retry

                        if attempt < MAX_RETRIES:
                            logger.warning(f"No listings on page {current_page} (attempt {attempt}/{MAX_RETRIES}), retrying...")
                            await page.wait_for_timeout(2000)

                    if load_error:
                        break

                    logger.info(f"Found {len(page_listings)} listings on page {current_page}")

                    if not page_listings:
                        consecutive_empty_pages += 1
                        logger.warning(
                            f"No listings found on page {current_page} after {MAX_RETRIES} attempts "
                            f"({consecutive_empty_pages}/{MAX_CONSECUTIVE_EMPTY} consecutive empty pages)"
                        )
                        if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY:
                            logger.warning(f"{MAX_CONSECUTIVE_EMPTY} consecutive empty pages — stopping pagination")
                            break
                    else:
                        consecutive_empty_pages = 0

                    listings.extend(page_listings)

                    # Stop early if the API told us the total page count
                    if meta_data:
                        total_count = (
                            meta_data.get('searchResultsCount')
                            or meta_data.get('totalCount')
                            or meta_data.get('total')
                            or 0
                        )
                        if total_count:
                            items_per_page = 120
                            total_pages = (total_count + items_per_page - 1) // items_per_page
                            if current_page >= total_pages:
                                logger.info(f"Last page reached ({current_page}/{total_pages}), stopping pagination")
                                break
                            logger.info(f"Pagination: page {current_page}/{total_pages}")

                    page_index += 1
                    current_page += 1

                    # Rate limiting between pages
                    await page.wait_for_timeout(int(self.request_delay * 1000))

                await browser.close()

        except Exception as e:
            logger.error(f"Error during scraping: {e}", exc_info=True)
            raise

        logger.info(f"Successfully scraped {len(listings)} total listings across {current_page} pages")
        return listings

    def _build_page_url(self, page_index: int) -> str:
        """
        Build the Nellis search URL for a given 0-based page index.

        Nellis uses _p1=s%3A120%2Cn%3A{page_index} (decoded: s:120,n:{page_index})
        where s is page size (120) and n is the 0-based page offset.
        """
        base = re.sub(r'[&?]_p1=[^&]*', '', self.base_url)
        separator = '&' if '?' in base else '?'
        return f"{base}{separator}_p1=s%3A120%2Cn%3A{page_index}"

    async def _extract_listings_from_page(self, page) -> List[Dict[str, Any]]:
        """
        Extract listings from the page's JavaScript context (Remix framework).

        Args:
            page: Playwright page object

        Returns:
            List of listing dictionaries
        """
        result = await page.evaluate('''() => {
            const RESULT_KEYS = ['products', 'searchResults', 'listings', 'items', 'results'];

            function extractFromLoaderData(loaderData) {
                for (const routeId of Object.keys(loaderData)) {
                    const data = loaderData[routeId];
                    if (!data) continue;
                    for (const key of RESULT_KEYS) {
                        if (Array.isArray(data[key]) && data[key].length > 0) {
                            return { results: data[key], meta: data };
                        }
                    }
                }
                return null;
            }

            // Remix v2+Vite: client router state (populated after navigation, takes priority)
            if (window.__remixRouter && window.__remixRouter.state && window.__remixRouter.state.loaderData) {
                const found = extractFromLoaderData(window.__remixRouter.state.loaderData);
                if (found) return found;
            }

            // Remix v2 SSR: data lives in __remixContext.state.loaderData
            if (window.__remixContext && window.__remixContext.state && window.__remixContext.state.loaderData) {
                const found = extractFromLoaderData(window.__remixContext.state.loaderData);
                if (found) return found;
            }

            // Remix v1: __remixRouteData with actionData/loaderData
            if (window.__remixRouteData) {
                for (const key of Object.keys(window.__remixRouteData)) {
                    const routeData = window.__remixRouteData[key];
                    if (!routeData) continue;
                    const data = routeData.actionData || routeData.loaderData || routeData;
                    if (!data) continue;
                    for (const rk of RESULT_KEYS) {
                        if (Array.isArray(data[rk]) && data[rk].length > 0) {
                            return { results: data[rk], meta: data };
                        }
                    }
                }
            }

            // Log available window keys to aid debugging
            const remixKeys = Object.keys(window).filter(k => k.startsWith('__remix'));
            return { debug: remixKeys };
        }''')

        if result and result.get('results'):
            items = result['results']
            logger.info(f"Extracted {len(items)} listings from window JS context")
            return self._parse_remix_listings(items)

        if result and result.get('debug') is not None:
            logger.warning(f"No listing data in JS context. Remix window keys found: {result.get('debug')}")

        # HTML fallback
        logger.warning("Falling back to HTML parsing...")
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        return self._parse_page_listings(soup)
    
    def _build_listing_url(self, item: Dict, url_id) -> str:
        """
        Build the correct Nellis Auction listing URL.

        The correct format is /p/{slug}/{id}. Slug comes from the API response
        if available, otherwise is generated from the title.
        """
        if not url_id:
            return ''
        slug = (
            item.get('slug')
            or item.get('urlSlug')
            or item.get('handle')
            or item.get('url_slug')
        )
        if not slug:
            title = item.get('title', '') or item.get('name', '')
            if title:
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-')
        if slug:
            return f"https://nellisauction.com/p/{slug}/{url_id}"
        return f"https://nellisauction.com/p/{url_id}"

    def _parse_remix_listings(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """
        Normalize a list of raw listing dicts from a Remix API response.

        Sets the 'id' field from the listing's numeric id for deduplication.
        """
        listings = []
        for item in items:
            try:
                # 'id' is the numeric listing ID used in URLs; 'inventoryNumber' is
                # the internal inventory tracking number (different value, wrong for URLs)
                url_id = item.get('id') or item.get('inventoryNumber') or item.get('inventory_number')
                inv_num = item.get('inventoryNumber') or item.get('inventory_number') or url_id

                grade = item.get('grade')
                if isinstance(grade, dict):
                    rating = grade.get('rating', 0) or grade.get('stars', 0)
                elif isinstance(grade, (int, float)):
                    rating = grade
                else:
                    rating = 0

                location = item.get('location')
                location_name = location.get('name', '') if isinstance(location, dict) else str(location or '')

                listing = {
                    'id': str(url_id) if url_id else '',
                    'title': item.get('title', '') or item.get('name', ''),
                    'url': self._build_listing_url(item, url_id),
                    'price': item.get('currentPrice', 0) or item.get('price', 0),
                    'estimated_retail': item.get('retailPrice', 0) or item.get('estimatedRetail', 0),
                    'rating': int(round(float(rating))) if rating else 0,
                    'inventory_number': inv_num,
                    'location': location_name,
                    'bid_count': item.get('bidCount', 0),
                    'is_closed': item.get('isClosed', False),
                    'market_status': item.get('marketStatus', ''),
                    'category': item.get('category', '') or item.get('categoryName', ''),
                }

                if listing['title']:
                    listings.append(listing)
            except Exception as e:
                logger.debug(f"Error parsing listing item: {e}")
        return listings

    async def _find_next_page_url_js(self, page, current_url: str, meta_data: dict = None) -> str:
        """
        Find the URL for the next page using pagination data from the Remix API or DOM.

        Args:
            page: Playwright page object
            current_url: Current page URL
            meta_data: Optional dict from the Remix API response (contains searchResultsCount)

        Returns:
            Next page URL or None if no more pages
        """
        try:
            current_page_num = self._extract_page_number(current_url)
            next_page_num = current_page_num + 1
            items_per_page = 120  # Nellis shows 120 products per page

            def build_next_url(page_num):
                if 'page=' in current_url:
                    return re.sub(r'page=\d+', f'page={page_num}', current_url)
                separator = '&' if '?' in current_url else '?'
                return f"{current_url}{separator}page={page_num}"

            # Use totalCount from captured API response if available
            if meta_data:
                total_count = (
                    meta_data.get('searchResultsCount')
                    or meta_data.get('totalCount')
                    or meta_data.get('total')
                    or 0
                )
                if total_count:
                    total_pages = (total_count + items_per_page - 1) // items_per_page
                    if current_page_num < total_pages:
                        next_url = build_next_url(next_page_num)
                        logger.info(f"Pagination from API data: page {current_page_num}/{total_pages}, next: {next_url}")
                        return next_url
                    else:
                        logger.info(f"Last page reached ({current_page_num}/{total_pages})")
                        return None

            # Fallback: read totalCount from window Remix state
            total_count = await page.evaluate('''() => {
                function countFromLoaderData(loaderData) {
                    for (const data of Object.values(loaderData)) {
                        if (!data) continue;
                        const count = data.searchResultsCount || data.totalCount || data.total;
                        if (count) return count;
                    }
                    return null;
                }
                // Prefer __remixRouter (client state, most current after navigation)
                if (window.__remixRouter && window.__remixRouter.state && window.__remixRouter.state.loaderData) {
                    const count = countFromLoaderData(window.__remixRouter.state.loaderData);
                    if (count) return count;
                }
                if (window.__remixContext && window.__remixContext.state && window.__remixContext.state.loaderData) {
                    const count = countFromLoaderData(window.__remixContext.state.loaderData);
                    if (count) return count;
                }
                return null;
            }''')

            if total_count:
                total_pages = (total_count + items_per_page - 1) // items_per_page
                if current_page_num < total_pages:
                    next_url = build_next_url(next_page_num)
                    logger.info(f"Pagination from JS context: page {current_page_num}/{total_pages}, next: {next_url}")
                    return next_url
                return None

            # Final fallback: look for a next-page link in the DOM
            next_button_url = await page.evaluate('''() => {
                const nextLink = document.querySelector('a[rel="next"], a[aria-label*="next" i]');
                return nextLink ? nextLink.href : null;
            }''')

            if next_button_url:
                logger.info(f"Found next page link in DOM: {next_button_url}")
                return next_button_url

            return None

        except Exception as e:
            logger.debug(f"Error finding next page: {e}")
            return None
    
    def _parse_page_listings(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse listings from the page by extracting JSON data from script tags.
        
        The Nellis Auction site renders listings from JSON in a script tag,
        not as HTML elements, so we extract the JSON directly.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of listing dictionaries
        """
        listings = []
        
        try:
            # Find script tags with the JSON data
            scripts = soup.find_all('script', type=False)
            
            for script in scripts:
                if not script.string:
                    continue
                    
                script_content = script.string
                
                # Check if this script contains searchResults
                if 'searchResults' not in script_content:
                    continue
                
                try:
                    # Try to find and extract the JSON object
                    # Look for the pattern: "searchResults":[...
                    start_idx = script_content.find('{"searchResults"')
                    if start_idx == -1:
                        # Try alternative pattern
                        start_idx = script_content.find('"searchResults"')
                        if start_idx == -1:
                            continue
                    
                    # Find a reasonable end point for JSON extraction
                    # We'll look for the end of the searchResults array and the next major structure
                    # This is tricky because we ne ed to find the closing of the searchResults array
                    
                    if start_idx > 0:
                        # Adjust start to include opening brace
                        start_idx = script_content.rfind('{', 0, start_idx + 1)
                    
                    # Try to find a good ending point
                    # Look for ,"routes/search._ index or the end of a major object
                    end_patterns = ['"routes/search._index"', '</script>', 'window.__remixRouteModules']
                    end_idx = len(script_content)
                    
                    for pattern in end_patterns:
                        idx = script_content.find(pattern, start_idx)
                        if idx > start_idx:
                            end_idx = min(end_idx, idx)
                    
                    if start_idx == -1 or end_idx <= start_idx:
                        continue
                    
                    json_str = script_content[start_idx:end_idx]
                    
                    #  Clean up the JSON string
                    json_str = json_str.rstrip('},')
                    if not json_str.endswith('}'):
                        # Try to find the last closing brace for the main object
                        last_brace = json_str.rfind('}')
                        if last_brace > 0:
                            json_str = json_str[:last_brace + 1]
                    
                    # Try to parse as JSON
                    data = json.loads(json_str)
                    
                    # Extract searchResults
                    search_results = data.get('searchResults', [])
                    if not isinstance(search_results, list):
                        continue
                    
                    logger.info(f"Found {len(search_results)} listings in JSON data")
                    
                    for item_data in search_results:
                        try:
                            url_id = item_data.get('id') or item_data.get('inventoryNumber')
                            listing = {
                                'title': item_data.get('title', ''),
                                'url': self._build_listing_url(item_data, url_id),
                                'price': item_data.get('currentPrice', 0),
                                'estimated_retail': item_data.get('retailPrice', 0),
                                'rating': item_data.get('grade', {}).get('rating', 0) if isinstance(item_data.get('grade'), dict) else 0,
                                'inventory_number': item_data.get('inventoryNumber'),
                                'location': item_data.get('location', {}).get('name', '') if isinstance(item_data.get('location'), dict) else '',
                                'bid_count': item_data.get('bidCount', 0),
                                'is_closed': item_data.get('isClosed', False),
                                'market_status': item_data.get('marketStatus', ''),
                                'category': item_data.get('category', ''),
                            }
                            
                            if listing['title']:  # Only add if title exists
                                listings.append(listing)
                        except Exception as e:
                            logger.debug(f"Error parsing individual listing: {e}")
                            continue
                    
                    if listings:
                        break  # Success - stop looking for more scripts
                        
                except (json.JSONDecodeError, ValueError, AttributeError) as e:
                    logger.debug(f"Could not parse script content as JSON: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error parsing page listings: {e}", exc_info=True)
        
        logger.info(f"Successfully parsed {len(listings)} listings from page")
        return listings
    
    def _find_next_page_url(self, soup: BeautifulSoup, current_url: str) -> str:
        """
        Find the URL for the next page of results.
        
        Args:
            soup: BeautifulSoup object of the current page
            current_url: Current page URL
            
        Returns:
            Next page URL or None if no more pages
        """
        try:
            logger.debug("Searching for pagination/next page link...")
            current_page_num = self._extract_page_number(current_url)
            
            # Strategy 1: Look for pagination nav with various class names
            pagination_selectors = [
                ('nav', {'class': 'pagination'}),
                ('div', {'class': 'pagination'}),
                ('nav', {'class': re.compile(r'paginat')}),
                ('div', {'class': re.compile(r'paginat')}),
                ('ul', {'class': re.compile(r'paginat')}),
            ]
            
            for tag, attrs in pagination_selectors:
                if isinstance(attrs.get('class'), str):
                    pagination = soup.find(tag, class_=attrs.get('class'))
                else:
                    pagination = soup.find(tag, attrs)
                
                if pagination:
                    logger.debug(f"Found pagination container: {tag} with {attrs}")
                    
                    # Look for "next" link
                    next_link = pagination.find('a', string=re.compile(r'next|Next|NEXT', re.I))
                    if not next_link:
                        next_link = pagination.find('a', {'rel': 'next'})
                    if not next_link:
                        # Look for links with arrow/chevron symbols
                        next_link = pagination.find('a', class_=re.compile(r'next|chevron|arrow|right', re.I))
                    if not next_link:
                        # Look for any link that suggests "next"
                        for link in pagination.find_all('a'):
                            link_text = link.get_text(strip=True)
                            if any(word in link_text.lower() for word in ['next', '>', '→', 'forward']):
                                next_link = link
                                break
                    
                    if next_link and next_link.get('href'):
                        next_url = next_link['href']
                        if not next_url.startswith('http'):
                            next_url = 'https://nellisauction.com' + next_url
                        logger.info(f"Found next page URL via pagination: {next_url}")
                        return next_url
            
            # Strategy 2: Look for page number links
            logger.debug(f"Trying page number strategy. Current page: {current_page_num}")
            page_links = soup.find_all('a', href=re.compile(r'[?&]page='))
            logger.debug(f"Found {len(page_links)} page links")
            
            if page_links:
                next_page_num = current_page_num + 1
                
                for link in page_links:
                    link_page_num = self._extract_page_number(link.get('href', ''))
                    if link_page_num == next_page_num:
                        next_url = link['href']
                        if not next_url.startswith('http'):
                            next_url = 'https://nellisauction.com' + next_url
                        logger.info(f"Found next page URL via page numbers: {next_url}")
                        return next_url
            
            # Strategy 3: Try to construct next URL manually using page parameter
            logger.debug("Trying manual URL construction...")
            next_page_num = current_page_num + 1
            if '&page=' in current_url:
                next_url = re.sub(r'&page=\d+', f'&page={next_page_num}', current_url)
                logger.info(f"Constructed next page URL manually: {next_url}")
                return next_url
            elif '?page=' in current_url:
                next_url = re.sub(r'\?page=\d+', f'?page={next_page_num}', current_url)
                logger.info(f"Constructed next page URL manually: {next_url}")
                return next_url
            else:
                # Try appending page parameter
                separator = '&' if '?' in current_url else '?'
                next_url = f"{current_url}{separator}page={next_page_num}"
                logger.info(f"Constructed next page URL with new parameter: {next_url}")
                return next_url
            
        except Exception as e:
            logger.warning(f"Error finding next page URL: {e}", exc_info=True)
            return None
    
    def _extract_page_number(self, url: str) -> int:
        """
        Extract page number from URL.
        
        Args:
            url: URL string
            
        Returns:
            Page number (default 1 if not found)
        """
        try:
            match = re.search(r'[?&]page=(\d+)', url)
            return int(match.group(1)) if match else 1
        except:
            return 1
    
    def _parse_listing_item(self, item) -> Dict[str, Any]:
        """
        Parse a single listing item from HTML.
        
        Returns:
            Dictionary with listing details or None if parsing fails
        """
        try:
            # Extract basic info
            title_elem = item.find('h2', class_='listing-title') or item.find('a', class_='product-title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # Extract URL
            url_elem = item.find('a', href=True)
            url = url_elem['href'] if url_elem else None
            if url and not url.startswith('http'):
                url = 'https://nellisauction.com' + url
            
            # Extract price
            price_elem = item.find('span', class_='current-price') or item.find('span', class_='price')
            price_text = price_elem.get_text(strip=True) if price_elem else "N/A"
            
            # Extract estimated retail price
            est_retail_elem = item.find(string=re.compile(r'EST\. RETAIL', re.I))
            if est_retail_elem:
                # Find the parent container and then the price value
                parent = est_retail_elem.parent
                if parent:
                    # Look for the next element that contains the price
                    next_elem = parent.find_next_sibling() or parent.find_next()
                    if next_elem:
                        est_retail_text = next_elem.get_text(strip=True)
                        # Clean up the price text
                        est_retail_text = re.sub(r'[^\d.]', '', est_retail_text)
                    else:
                        est_retail_text = "N/A"
                else:
                    est_retail_text = "N/A"
            else:
                # Try alternative method - look for text containing "EST. RETAIL"
                est_retail_text = "N/A"
                text_content = item.get_text()
                est_retail_match = re.search(r'EST\. RETAIL.*?\$?([\d,]+\.?\d*)', text_content, re.I)
                if est_retail_match:
                    est_retail_text = est_retail_match.group(1).replace(',', '')
            
            # Extract rating/stars
            rating = self._extract_rating(item)
            
            # Extract condition
            condition_elem = item.find('span', class_='condition') or item.find('div', class_='condition-badge')
            condition = condition_elem.get_text(strip=True) if condition_elem else "Unknown"
            
            # Extract image URL
            img_elem = item.find('img')
            image_url = img_elem.get('src') or img_elem.get('data-src') if img_elem else None
            
            # Extract item ID (usually in URL)
            item_id = self._extract_item_id(url)
            
            # Extract category
            category_elem = item.find('span', class_='category') or item.find('div', class_='category-badge')
            category = category_elem.get_text(strip=True) if category_elem else ""
            
            listing = {
                'id': item_id,
                'title': title,
                'url': url,
                'price': price_text,
                'estimated_retail': est_retail_text,
                'rating': rating,
                'condition': condition,
                'category': category,
                'image_url': image_url,
                'scraped_at': datetime.now().isoformat()
            }
            
            return listing
            
        except Exception as e:
            logger.debug(f"Error parsing listing item: {e}")
            return None
    
    def _extract_rating(self, item) -> int:
        """
        Extract star rating from listing item.
        
        Returns:
            Rating as integer (1-5), or 0 if not found
        """
        try:
            # Look for star rating element
            rating_elem = item.find('div', class_=['rating', 'stars', 'star-rating'])
            
            if not rating_elem:
                # Try to find by aria-label or data attribute
                rating_elem = item.find(attrs={'aria-label': re.compile(r'\d+ (star|out of)')})
            
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                # Extract number from text like "4.5 out of 5 stars"
                match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if match:
                    rating = float(match.group(1))
                    return int(round(rating))
            
            # Default to no rating found
            return 0
            
        except Exception as e:
            logger.debug(f"Error extracting rating: {e}")
            return 0
    
    def _extract_item_id(self, url: str) -> str:
        """
        Extract unique item ID from URL.
        
        Returns:
            Item ID string, or empty string if not found
        """
        try:
            if not url:
                return ""
            
            # Try to extract ID from URL pattern: /p/SLUG/ID
            match = re.search(r'/p/[^/]+/(\d+)', url)
            if match:
                return match.group(1)
            
            # Fallback: use full URL as ID
            return url
            
        except Exception:
            return ""
