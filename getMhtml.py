#!/usr/bin/env python3
"""
Get MHTML - Save a complete webpage as MHTML format using Playwright

Usage:
    python getMhtml.py <url> <output_dir> [options]
    
Examples:
    # Save webpage as MHTML to ./output directory
    python getMhtml.py https://example.com ./output
    
    # Save with custom timeout
    python getMhtml.py https://example.com ./output --timeout 30000
    
    # Use specific user agent
    python getMhtml.py https://example.com ./output --user-agent "Custom Agent"
    
    # Use proxy
    python getMhtml.py https://example.com ./output --proxy http://proxy.example.com:8080
    
    # Save as HTML instead of MHTML
    python getMhtml.py https://example.com ./output --format html
"""

import argparse
import sys
import os
import logging
from pathlib import Path
import asyncio
from typing import Optional
from playwright.async_api import async_playwright
import aiofiles

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_browser_context(p, url: str, timeout: int = 30000, user_agent: str = None, proxy: str = None):
    """
    Create browser context and navigate to URL using Playwright.
    
    Args:
        p: Playwright instance
        url: The URL to fetch
        timeout: Maximum navigation timeout in milliseconds
        user_agent: Custom user agent string
        proxy: Proxy URL (optional)
        
    Returns:
        Tuple of (browser, context, page)
    """
    # Launch browser (Chromium by default)
    launch_options = {'headless': True}
    
    if proxy:
        launch_options['proxy'] = {'server': proxy}
    
    browser = await p.chromium.launch(**launch_options)
    
    # Enhanced browser context options to avoid bot detection
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'zh-CN',
        'timezone_id': 'Asia/Shanghai',
        'geolocation': {'latitude': 31.2304, 'longitude': 121.4737},
        'permissions': ['geolocation'],
        'color_scheme': 'light',
        'reduced_motion': 'reduce',
        'extra_http_headers': {
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    }
    
    if user_agent:
        context_options['user_agent'] = user_agent
    else:
        context_options['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    
    try:
        logger.info(f"Navigating to {url}")
        try:
            await page.goto(url, wait_until='networkidle', timeout=timeout)
        except Exception as e:
            logger.warning(f"Navigation timeout occurred: {e}")
            logger.info("Stopping page loading and continuing with already loaded content...")
            # Stop page loading
            await page.evaluate("window.stop()")
        
        # Wait for any dynamic content to load
        try:
            await page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception:
            logger.info("Continuing with current page state...")
        
        # Wait for page to be fully loaded
        logger.info("Waiting for page to be fully loaded...")
        try:
            # Wait for DOM to be stable
            await page.wait_for_load_state('domcontentloaded')
            # Additional wait for network idle
            await page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            logger.warning(f"Timeout waiting for full load: {e}")
        
        logger.info(f"Successfully loaded page from {url}")
        
        return browser, context, page
        
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        # Clean up on error
        await page.close()
        await context.close()
        await browser.close()
        raise


async def save_page_as_mhtml(page, output_path: Path) -> bool:
    """
    Save the current page as MHTML format.
    
    Args:
        page: Playwright page object
        output_path: Path where MHTML file will be saved
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Saving page as MHTML to: {output_path}")
        
        # Use CDP session to save as MHTML
        cdp_session = await page.context.new_cdp_session(page)
        
        # Get the page frame tree
        result = await cdp_session.send('Page.getFrameTree')
        frame_tree = result['frameTree']
        
        # Save as MHTML
        mhtml_result = await cdp_session.send('Page.captureSnapshot', {
            'format': 'mhtml'
        })
        
        mhtml_data = mhtml_result['data']
        
        # Write MHTML data to file
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(mhtml_data)
        
        logger.info(f"MHTML saved successfully: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving as MHTML: {e}")
        return False


async def save_page_as_html(page, output_dir: Path) -> bool:
    """
    Save the current page as HTML with resources.
    
    Args:
        page: Playwright page object
        output_dir: Directory where HTML and resources will be saved
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Saving page as HTML to: {output_dir}")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create resources directory
        resources_dir = output_dir / "resources"
        resources_dir.mkdir(exist_ok=True)
        
        # Step 1: Save the page HTML
        html_content = await page.content()
        html_file = output_dir / "page.html"
        
        async with aiofiles.open(html_file, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        
        logger.info(f"HTML saved to: {html_file}")
        
        # Step 2: Get all resources (images, CSS, JS, etc.)
        # Note: This is a simplified approach. For a complete solution,
        # we would need to intercept and save all network requests.
        
        # Get all image URLs from the page
        js_code = """
        () => {
            const resources = [];
            
            // Get all images
            const images = document.querySelectorAll('img');
            for (const img of images) {
                if (img.src && !img.src.startsWith('data:')) {
                    resources.push({
                        url: img.src,
                        type: 'image',
                        element: 'img'
                    });
                }
            }
            
            // Get all stylesheets
            const links = document.querySelectorAll('link[rel="stylesheet"]');
            for (const link of links) {
                if (link.href) {
                    resources.push({
                        url: link.href,
                        type: 'stylesheet',
                        element: 'link'
                    });
                }
            }
            
            // Get all scripts
            const scripts = document.querySelectorAll('script[src]');
            for (const script of scripts) {
                if (script.src) {
                    resources.push({
                        url: script.src,
                        type: 'script',
                        element: 'script'
                    });
                }
            }
            
            return resources;
        }
        """
        
        resources_info = await page.evaluate(js_code)
        
        if resources_info:
            logger.info(f"Found {len(resources_info)} resources to save")
            
            # Download and save each resource
            for i, resource in enumerate(resources_info, 1):
                try:
                    # Add small delay to avoid rate limiting
                    if i > 1:
                        await asyncio.sleep(0.5)
                    
                    # Download resource
                    response = await page.request.get(resource['url'])
                    
                    if response.ok:
                        # Get the response body
                        data = await response.body()
                        
                        # Create a safe filename
                        import hashlib
                        url_hash = hashlib.md5(resource['url'].encode()).hexdigest()[:8]
                        ext = resource['url'].split('.')[-1].split('?')[0] if '.' in resource['url'] else 'bin'
                        if len(ext) > 10:  # Sanity check
                            ext = 'bin'
                        
                        filename = f"{resource['type']}_{i:03d}_{url_hash}.{ext}"
                        filepath = resources_dir / filename
                        
                        # Save to resources directory
                        async with aiofiles.open(filepath, 'wb') as f:
                            await f.write(data)
                        
                        logger.debug(f"Saved resource {i}/{len(resources_info)}: {resource['url']}")
                    else:
                        logger.warning(f"Failed to download resource {i}: {resource['url']} - HTTP {response.status}")
                        
                except Exception as e:
                    logger.warning(f"Error downloading resource {i}: {e}")
        
        logger.info(f"Page saved successfully to: {output_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving as HTML: {e}")
        return False


async def main_async(args):
    """Main async function."""
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
    
    # Create output directory path
    output_dir = Path(args.output_dir)
    
    playwright_instance = None
    browser = None
    context = None
    page = None
    
    try:
        # Create Playwright instance
        playwright_instance = await async_playwright().start()
        
        # Step 1: Create browser context and navigate to URL
        logger.info(f"Creating browser context and navigating to {args.url}")
        browser, context, page = await create_browser_context(
            playwright_instance,
            args.url, 
            timeout=args.timeout,
            user_agent=args.user_agent,
            proxy=args.proxy
        )
        
        # Step 2: Save the page
        success = False
        if args.format.lower() == 'mhtml':
            # Save as MHTML
            output_path = output_dir / f"page_{hash(args.url) % 10000:04d}.mhtml"
            output_dir.mkdir(parents=True, exist_ok=True)
            success = await save_page_as_mhtml(page, output_path)
            
            if success:
                print("\n" + "="*60)
                print("PAGE SAVE SUMMARY")
                print("="*60)
                print(f"URL: {args.url}")
                print(f"Format: MHTML")
                print(f"Saved to: {output_path.absolute()}")
                print(f"File size: {output_path.stat().st_size:,} bytes" if output_path.exists() else "File not found")
                print("="*60)
        else:
            # Save as HTML with resources
            success = await save_page_as_html(page, output_dir)
            
            if success:
                print("\n" + "="*60)
                print("PAGE SAVE SUMMARY")
                print("="*60)
                print(f"URL: {args.url}")
                print(f"Format: HTML with resources")
                print(f"Saved to: {output_dir.absolute()}")
                print(f"Files created:")
                print(f"  HTML: {output_dir / 'page.html'}")
                print(f"  Resources: {output_dir / 'resources'}/")
                print("="*60)
        
        if not success:
            logger.error("Failed to save the page")
            print("\nERROR: Failed to save the page. Check logs for details.")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise
    finally:
        # Clean up browser resources
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Save a complete webpage as MHTML or HTML format using Playwright',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s https://example.com ./output
  %(prog)s https://example.com ./output --timeout 30000
  %(prog)s https://example.com ./output --user-agent "Custom Agent"
  %(prog)s https://example.com ./output --proxy http://proxy.example.com:8080
  %(prog)s https://example.com ./output --format html
  %(prog)s https://example.com ./output --verbose
        """
    )
    
    parser.add_argument(
        'url',
        help='URL of the web page to save'
    )
    
    parser.add_argument(
        'output_dir',
        help='Directory where the saved page will be stored'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30000,
        help='Navigation timeout in milliseconds (default: 30000)'
    )
    
    parser.add_argument(
        '--user-agent',
        help='Custom user agent string'
    )
    
    parser.add_argument(
        '--proxy',
        help='Proxy URL (e.g., http://proxy.example.com:8080)'
    )
    
    parser.add_argument(
        '--format',
        choices=['mhtml', 'html'],
        default='mhtml',
        help='Output format: mhtml (single file) or html (with separate resources) (default: mhtml)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle Windows-specific asyncio issues
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        # Run the main async function
        asyncio.run(main_async(args))
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
