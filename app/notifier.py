"""
Notifier module for sending email notifications.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        from_email: str,
        password: str,
        recipient_email: str,
        use_tls: bool = True,
        subject_template: str = "Nellis Auction - New Listings: {count} Items"
    ):
        """
        Initialize the email notifier.
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            from_email: Sender email address
            password: Email password/app password
            recipient_email: Recipient email address
            use_tls: Whether to use TLS
            subject_template: Subject line template with {count} placeholder
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.password = password
        self.recipient_email = recipient_email
        self.use_tls = use_tls
        self.subject_template = subject_template
    
    def send_notification(self, listings: List[Dict[str, Any]]) -> bool:
        """
        Send email notification with matched listings.
        
        Args:
            listings: List of matched listing dictionaries
        
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            if not listings:
                logger.warning("No listings to send notification for")
                return False
            
            with_images = sum(1 for l in listings if l.get('image_url'))
            logger.info(f"Sending notification: {len(listings)} listings, {with_images} with images")

            # Create email
            subject = self.subject_template.format(count=len(listings))
            html_body = self._generate_html_body(listings)
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = self.recipient_email
            
            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Connect to SMTP server and send
            masked_password = (self.password[:2] + '*' * (len(self.password) - 4) + self.password[-2:]) if self.password and len(self.password) > 4 else '(empty or too short)'
            logger.info(f"SMTP login username: '{self.from_email}'")
            logger.info(f"SMTP login password: '{masked_password}' (length: {len(self.password) if self.password else 0})")
            logger.info(f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port}")

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                server.login(self.from_email, self.password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {self.recipient_email} with {len(listings)} listings")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    def _generate_html_body(self, listings: List[Dict[str, Any]]) -> str:
        """
        Generate HTML email body with listings.
        
        Args:
            listings: List of listing dictionaries
        
        Returns:
            HTML string for email body
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        listings_html = ""
        for listing in listings:
            listings_html += self._format_listing_item(listing)
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-bottom: 2px solid #ddd; }}
                .header h1 {{ margin: 0; color: #333; }}
                .header p {{ margin: 5px 0 0 0; color: #666; font-size: 14px; }}
                .listings {{ padding: 20px; }}
                .listing-item {{ 
                    border: 1px solid #ddd; 
                    border-radius: 5px; 
                    padding: 15px; 
                    margin-bottom: 15px;
                    background-color: #fafafa;
                }}
                .listing-title {{ font-size: 18px; font-weight: bold; color: #0066cc; margin: 0 0 10px 0; }}
                .listing-details {{ margin: 10px 0; font-size: 14px; }}
                .listing-detail {{ margin: 5px 0; }}
                .label {{ font-weight: bold; color: #555; display: inline-block; width: 110px; }}
                .price {{ color: #00aa00; font-weight: bold; font-size: 16px; }}
                .rating {{ color: #ff9800; }}
                .link {{ margin-top: 10px; }}
                .link a {{ 
                    background-color: #0066cc; 
                    color: white; 
                    padding: 8px 12px; 
                    text-decoration: none; 
                    border-radius: 3px; 
                    display: inline-block;
                }}
                .link a:hover {{ background-color: #0052a3; }}
                .footer {{ background-color: #f0f0f0; padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Nellis Auction - New Listings Found</h1>
                    <p>Timestamp: {timestamp}</p>
                </div>
                
                <div class="listings">
                    {listings_html}
                </div>
                
                <div class="footer">
                    <p>Nellis Auction Monitor - Delran NJ Location</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_listing_item(self, listing: Dict[str, Any]) -> str:
        """
        Format a single listing item as HTML.
        
        Args:
            listing: Listing dictionary
        
        Returns:
            HTML string for the listing item
        """
        title = listing.get('title', 'Unknown')
        price = listing.get('price', 'N/A')
        estimated_retail = listing.get('estimated_retail', 'N/A')
        rating = listing.get('rating', 0)
        url = listing.get('url', '#')
        image_url = listing.get('image_url', '')
        matched_keywords = listing.get('matched_keywords', [])

        rating_stars = '⭐' * rating if rating > 0 else 'Not rated'
        keywords_html = ', '.join(f'<strong>{kw}</strong>' for kw in matched_keywords) if matched_keywords else 'N/A'

        if image_url:
            logger.debug(f"Image URL for '{title}': {image_url}")
            image_cell = f"""
                <td style="width:200px; min-width:200px; vertical-align:top; padding-right:15px;">
                    <a href="{url}" target="_blank">
                        <img src="{image_url}" width="200"
                             style="display:block; width:200px; max-height:200px; object-fit:contain; border-radius:4px; border:1px solid #ddd;">
                    </a>
                </td>"""
        else:
            image_cell = ""

        return f"""
        <div class="listing-item">
            <table cellpadding="0" cellspacing="0" border="0" style="width:100%;">
                <tr>
                    {image_cell}
                    <td style="vertical-align:top;">
                        <div class="listing-title">{title}</div>
                        <div class="listing-details">
                            <div class="listing-detail"><span class="label">Price:</span> <span class="price">{price}</span></div>
                            <div class="listing-detail"><span class="label">Est. Retail:</span> ${estimated_retail}</div>
                            <div class="listing-detail"><span class="label">Keywords:</span> {keywords_html}</div>
                            <div class="listing-detail"><span class="label">Rating:</span> <span class="rating">{rating_stars}</span></div>
                        </div>
                        <div class="link"><a href="{url}" target="_blank">View Listing</a></div>
                    </td>
                </tr>
            </table>
        </div>
        """
