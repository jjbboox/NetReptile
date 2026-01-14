#!/usr/bin/env python3
"""
NetReptile - A web page content fetcher using Playwright

Usage:
    python netreptile.py <url> <output_file>
    
Basic Examples:
    python netreptile.py https://example.com page.html
    python netreptile.py "https://www.google.com" google.html --timeout 60000

Container Extraction Examples:
    python netreptile.py https://news.example.com news.txt --selector ".article-content"
    python netreptile.py https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath
"""

import asyncio
import sys
import argparse
from pathlib import Path
from playwright.async_api import async_playwright
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def fetch_page_content(url: str, timeout: int = 30000, selector: str = None, selector_type: str = 'css') -> str:
    """
    Fetch web page content using Playwright.
    
    Args:
        url: The URL to fetch
        timeout: Maximum navigation timeout in milliseconds
        selector: CSS selector or XPath to find specific containers (optional)
        selector_type: Type of selector - 'css' or 'xpath' (default: 'css')
        
    Returns:
        The page HTML content as a string, or extracted text if selector is provided
    """
    async with async_playwright() as p:
        # Launch browser (Chromium by default)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            logger.info(f"Navigating to {url}")
            await page.goto(url, wait_until='networkidle', timeout=timeout)
            
            # Wait for any dynamic content to load
            await page.wait_for_load_state('networkidle')
            
            # If selector is provided, extract text from matching elements
            if selector:
                logger.info(f"Extracting text from containers matching selector: {selector} (type: {selector_type})")
                
                if selector_type == 'css':
                    elements = await page.query_selector_all(selector)
                elif selector_type == 'xpath':
                    elements = await page.query_selector_all(f'xpath={selector}')
                else:
                    raise ValueError(f"Unsupported selector type: {selector_type}. Use 'css' or 'xpath'.")
                
                if not elements:
                    logger.warning(f"No elements found matching selector: {selector}")
                    return ""
                
                # Extract text from all matching elements
                extracted_texts = []
                for i, element in enumerate(elements):
                    try:
                        text = await element.text_content()
                        if text and text.strip():
                            extracted_texts.append(text.strip())
                            logger.debug(f"Extracted text from element {i+1}: {text[:100]}...")
                    except Exception as e:
                        logger.warning(f"Failed to extract text from element {i+1}: {e}")
                
                if not extracted_texts:
                    logger.warning("No text content found in matching elements")
                    return ""
                
                # Join all extracted texts with separators
                separator = "\n" + "="*80 + "\n"
                content = separator.join(extracted_texts)
                logger.info(f"Successfully extracted text from {len(extracted_texts)} containers")
                
            else:
                # Get the complete HTML content
                content = await page.content()
                logger.info(f"Successfully fetched full HTML content from {url}")
            
            return content
            
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
        finally:
            await browser.close()


def save_content(content: str, output_file: str) -> None:
    """
    Save content to a file.
    
    Args:
        content: The content to save
        output_file: Path to the output file
    """
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Content saved to {output_file}")
        print(f"Successfully saved page content to: {output_file}")
        
    except Exception as e:
        logger.error(f"Error saving to {output_file}: {e}")
        raise


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Fetch web page content using Playwright and save to file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com output.html
  %(prog)s "https://www.google.com" google.html --timeout 60000
  %(prog)s https://news.example.com news.txt --selector ".article-content"
  %(prog)s https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath
        """
    )
    
    parser.add_argument(
        'url',
        help='URL of the web page to fetch'
    )
    
    parser.add_argument(
        'output_file',
        help='Path to the output file where content will be saved'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30000,
        help='Navigation timeout in milliseconds (default: 30000)'
    )
    
    parser.add_argument(
        '--selector',
        help='CSS selector or XPath to find specific containers for text extraction'
    )
    
    parser.add_argument(
        '--selector-type',
        choices=['css', 'xpath'],
        default='css',
        help='Type of selector: css or xpath (default: css)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()


async def main_async():
    """Main async function."""
    args = parse_arguments()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")
    
    # Validate URL
    if not args.url.startswith(('http://', 'https://')):
        logger.warning(f"URL doesn't start with http:// or https://: {args.url}")
        # Try to add https:// if missing
        args.url = f"https://{args.url}"
        logger.info(f"Trying with: {args.url}")
    
    try:
        # Fetch page content
        content = await fetch_page_content(
            args.url, 
            args.timeout, 
            selector=args.selector,
            selector_type=args.selector_type
        )
        
        # Save to file
        save_content(content, args.output_file)
        
    except Exception as e:
        logger.error(f"Failed to process {args.url}: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
