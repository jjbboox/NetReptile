#!/usr/bin/env python3
"""
NetReptile - A web page content fetcher using Playwright

Usage:
    python netreptile.py <url> <output_file>
    python netreptile.py --list <url_list_file> <output_file>
    
Basic Examples:
    python netreptile.py https://example.com page.html
    python netreptile.py "https://www.google.com" google.html --timeout 60000

Container Extraction Examples:
    python netreptile.py https://news.example.com news.txt --selector ".article-content"
    python netreptile.py https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath

URL List Examples:
    python netreptile.py --list urls.txt output.txt
    python netreptile.py --list urls.txt output.txt --config config.json
    python netreptile.py --list urls.txt output.txt --selector ".article" --timeout 60000
"""

import asyncio
import sys
import argparse
import json
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
        
        navigation_timeout_occurred = False
        
        try:
            logger.info(f"Navigating to {url}")
            try:
                await page.goto(url, wait_until='networkidle', timeout=timeout)
            except TimeoutError as e:
                logger.warning(f"Navigation timeout occurred: {e}")
                logger.info("Stopping page loading and continuing with already loaded content...")
                navigation_timeout_occurred = True
                # Stop page loading
                await page.evaluate("window.stop()")
            
            # Wait for any dynamic content to load (with timeout handling)
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)  # Shorter timeout for load state
            except TimeoutError as e:
                if not navigation_timeout_occurred:
                    logger.warning(f"Load state timeout occurred: {e}")
                    logger.info("Continuing with current page state...")
            
            # If selector is provided, extract text from matching elements
            print(f"selector: ", selector)
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


def load_config(config_path):
    """
    Load configuration from a JSON file.
    
    Args:
        config_path: Path to the JSON configuration file
        
    Returns:
        dict: Configuration dictionary with keys: timeout, selector, selector_type, baseurl
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Validate and normalize config
        valid_config = {}
        
        if 'timeout' in config:
            try:
                valid_config['timeout'] = int(config['timeout'])
            except (ValueError, TypeError):
                logger.warning(f"Invalid timeout value in config: {config['timeout']}, using default")
        
        if 'selector' in config:
            valid_config['selector'] = str(config['selector'])
        
        if 'selector_type' in config:
            selector_type = str(config['selector_type']).lower()
            if selector_type in ['css', 'xpath']:
                valid_config['selector_type'] = selector_type
            else:
                logger.warning(f"Invalid selector_type in config: {config['selector_type']}, using default")
        
        if 'baseurl' in config:
            baseurl = str(config['baseurl']).strip()
            # Ensure baseurl ends with a slash for proper URL concatenation
            if baseurl and not baseurl.endswith('/'):
                baseurl += '/'
            valid_config['baseurl'] = baseurl
            logger.debug(f"Loaded baseurl from config: {baseurl}")
        
        logger.info(f"Loaded configuration from {config_path}")
        return valid_config
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file {config_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading configuration from {config_path}: {e}")
        raise


def load_url_list(list_file):
    """
    Load URLs from a list file (one URL per line).
    
    Args:
        list_file: Path to the file containing URLs
        
    Returns:
        list: List of URLs
    """
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        urls = []
        for line in lines:
            # Skip comments
            if line.startswith('#'):
                continue
            
            # Check if line contains an <a href> tag
            if '<a href=' in line.lower() or '<a href =' in line.lower():
                # Try to extract URL from href attribute
                import re
                # Match href attribute with single or double quotes
                match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    logger.debug(f"Extracted URL from <a href> tag: {url}")
                    urls.append(url)
                else:
                    logger.warning(f"Could not extract URL from <a href> tag: {line}")
            else:
                # Regular URL line
                urls.append(line)
        
        logger.info(f"Loaded {len(urls)} URLs from {list_file}")
        return urls
        
    except FileNotFoundError:
        logger.error(f"List file not found: {list_file}")
        raise
    except Exception as e:
        logger.error(f"Error loading URL list from {list_file}: {e}")
        raise


async def process_single_url(url, timeout, selector, selector_type, baseurl=None):
    """
    Process a single URL and return its content.
    
    Args:
        url: URL to process
        timeout: Navigation timeout in milliseconds
        selector: CSS selector or XPath for text extraction
        selector_type: Type of selector
        baseurl: Base URL to prepend to relative URLs (optional)
        
    Returns:
        str: Extracted content
    """
    # Apply baseurl if provided and URL is relative
    if baseurl and not url.startswith(('http://', 'https://', '//')):
        # Check if URL starts with a slash (absolute path relative to baseurl)
        if url.startswith('/'):
            # Remove leading slash from URL if baseurl already ends with slash
            if baseurl.endswith('/'):
                url = url[1:]
        # Concatenate baseurl and URL
        original_url = url
        url = baseurl + url
        logger.info(f"Applied baseurl to relative URL: {original_url} -> {url}")
    
    # Validate and normalize URL
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"URL doesn't start with http:// or https://: {url}")
        # Try to add https:// if missing
        url = f"https://{url}"
        logger.info(f"Trying with: {url}")
    
    try:
        content = await fetch_page_content(
            url, 
            timeout, 
            selector=selector,
            selector_type=selector_type
        )
        return content
    except Exception as e:
        logger.error(f"Failed to process {url}: {e}")
        return None


async def main_async_with_args(args):
    """Main async function that takes already parsed arguments."""
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")
    
    # Validate arguments
    if not args.list_file and not args.url:
        logger.error("Either a URL or --list option must be provided")
        print("Error: Either a URL or --list option must be provided")
        print("Usage: python netreptile.py <url> <output_file> [options]")
        print("       python netreptile.py --list <url_list_file> <output_file> [options]")
        sys.exit(1)
    
    # Load configuration from file if specified
    config = {}
    if args.config:
        try:
            config = load_config(args.config)
            logger.info(f"Configuration loaded: {config}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)
    
    # Determine final parameter values (command line overrides config)
    timeout = args.timeout if args.timeout is not None else config.get('timeout', 30000)
    selector = args.selector if args.selector is not None else config.get('selector')
    selector_type = args.selector_type if args.selector_type is not None else config.get('selector_type', 'css')
    baseurl = config.get('baseurl')  # Get baseurl from config if exists
    
    logger.debug(f"Final parameters - timeout: {timeout}, selector: {selector}, selector_type: {selector_type}, baseurl: {baseurl}")
    
    # Process based on whether we have a list file or single URL
    if args.list_file:
        # Process list of URLs
        try:
            urls = load_url_list(args.list_file)
            if not urls:
                logger.error(f"No valid URLs found in {args.list_file}")
                sys.exit(1)
            
            logger.info(f"Processing {len(urls)} URLs from {args.list_file}")
            
            successful_urls = 0
            
            # Create or truncate output file at the beginning
            output_path = Path(args.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Start with empty file
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write("")
            
            for i, url in enumerate(urls, 1):
                # Print progress in format [i/total]
                print(f"[{i}/{len(urls)}] Processing: {url}")
                logger.info(f"Processing URL {i}/{len(urls)}: {url}")
                
                content = await process_single_url(url, timeout, selector, selector_type, baseurl)
                
                if content is not None:
                    successful_urls += 1
                    
                    # Add URL header and separator
                    url_header = f"\n{'='*80}\nURL {i}: {url}\n{'='*80}\n"
                    
                    # Append content to output file immediately
                    with open(args.output_file, 'a', encoding='utf-8') as f:
                        if i > 1:  # Add separator before content if not first URL
                            f.write(url_header)
                        else:  # First URL, just write header without leading newline
                            f.write(url_header.lstrip())
                        
                        f.write(content)
                    
                    print(f"[{i}/{len(urls)}] Successfully processed and saved: {url}")
            
            if successful_urls == 0:
                logger.error("Failed to process any URLs from the list")
                sys.exit(1)
            
            logger.info(f"Successfully processed {successful_urls}/{len(urls)} URLs and saved to {args.output_file}")
            print(f"Successfully processed {successful_urls}/{len(urls)} URLs and saved to: {args.output_file}")
            
        except Exception as e:
            logger.error(f"Failed to process URL list: {e}")
            sys.exit(1)
    
    else:
        # Process single URL (original behavior)
        print(f"args.url: {args.url}")
        
        try:
            content = await process_single_url(args.url, timeout, selector, selector_type, baseurl)
            
            if content is None:
                logger.error(f"Failed to process {args.url}")
                sys.exit(1)
            
            # Save to file
            save_content(content, args.output_file)
            
        except Exception as e:
            logger.error(f"Failed to process {args.url}: {e}")
            sys.exit(1)


def main():
    """Main entry point."""
    # Parse arguments synchronously first to handle --help without entering async context
    parser = argparse.ArgumentParser(
        description='Fetch web page content using Playwright and save to file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com output.html
  %(prog)s "https://www.google.com" google.html --timeout 60000
  %(prog)s https://news.example.com news.txt --selector ".article-content"
  %(prog)s https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath
  %(prog)s https://example.com output.html --config config.json
  %(prog)s https://example.com output.html --config config.json --timeout 50000
  %(prog)s --list urls.txt output.txt --config config.json
        """
    )
    
    parser.add_argument(
        'url',
        nargs='?',  # Make URL optional when --list is used
        help='URL of the web page to fetch (ignored when --list is specified)'
    )
    
    parser.add_argument(
        'output_file',
        help='Path to the output file where content will be saved'
    )
    
    parser.add_argument(
        '--config',
        help='Path to JSON configuration file (can contain timeout, selector, selector_type)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=None,
        help='Navigation timeout in milliseconds (overrides config file if provided)'
    )
    
    parser.add_argument(
        '--selector',
        help='CSS selector or XPath to find specific containers for text extraction (overrides config file if provided)'
    )
    
    parser.add_argument(
        '--selector-type',
        choices=['css', 'xpath'],
        default=None,
        help='Type of selector: css or xpath (overrides config file if provided)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--list',
        dest='list_file',
        help='Path to a file containing a list of URLs (one per line). When specified, ignores the URL argument and processes all URLs in the list.'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle Windows-specific asyncio issues
    if sys.platform == 'win32':
        # Try to use ProactorEventLoop for better Windows compatibility
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = None
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the main async function with the parsed arguments
        loop.run_until_complete(main_async_with_args(args))
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Clean up the event loop
        if loop:
            try:
                # Cancel all running tasks
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()
                
                # Run loop until all tasks are cancelled
                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                
                # Shutdown async generators
                loop.run_until_complete(loop.shutdown_asyncgens())
                
                # Close the loop
                loop.close()
            except Exception:
                pass  # Ignore errors during cleanup


if __name__ == "__main__":
    main()
