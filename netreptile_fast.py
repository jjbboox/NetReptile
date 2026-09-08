#!/usr/bin/env python3
"""
NetReptile-Fast - 高性能网页抓取程序（基于原 NetReptile 的功能重构）

相对原版 netreptile.py 的主要优化：
  1) 批量(--list)模式全程复用同一个浏览器实例，避免每个 URL 都冷启动浏览器。
  2) 可控并发：--parallel N（默认 3），多个页面在同一个浏览器内并行加载。
  3) 移除写死的 time.sleep(1.0)；可选 --delay(毫秒，默认 0) 礼貌间隔，
     且使用非阻塞 asyncio.sleep。
  4) 导航等待策略可配置：--wait-until domcontentloaded|load|networkidle。
     默认为 domcontentloaded + 短暂 settle（默认 3 秒 networkidle 宽限），
     避免把整个 timeout 浪费在"永不空闲"的长连接页面上。
  5) 输出文件只打开一次；统计/日志在内存汇总后统一写入。
  6) 修复原版 bug：--list 无论成败都退出码 1；新版为：
        - 有内容成功 -> 退出码 0
        - 存在处理失败(error)或全部失败 -> 退出码 1
     仅当出现 warning/error 时才向 warning_error_url.log 追加记录。

与 fix_errors.py / selector_processor.py 的兼容性：
  - selector_processor 模块不改动，仍被本程序 import 复用。
  - 若你希望 fix_errors.py 也能享受"复用浏览器/并发"：
    可把 fix_errors.py 中对 netreptile 的导入换成 netreptile_fast（本程序提供等价的
    fetch_page_content / fetch_page_content_with_selectors / load_config /
    format_content_with_timeout_markers，且 fetch 系列保持可独立启动浏览器）。

用法（与原版一致，另加新参数）：
    python netreptile_fast.py <url> <output_file>
    python netreptile_fast.py --list <url_list_file> <output_file> [--config config.json]
    python netreptile_fast.py --list urls.txt out.txt --config config/6park.json --parallel 4
"""

import asyncio
import sys
import logging
from datetime import datetime
import argparse
import json
import re
from pathlib import Path
import uuid
from playwright.async_api import async_playwright
from selector_processor import process_selectors

# Playwright 的超时异常类；某些构建只导出 inner impl，因此做兼容导入
try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except Exception:
    PlaywrightTimeoutError = asyncio.TimeoutError

# ---------------------------------------------------------------------------
# Config / Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30000          # ms
DEFAULT_PARALLEL = 3
DEFAULT_SETTLE_TIMEOUT = 3000    # ms：domcontentloaded/load 后 networkidle 宽限
DEFAULT_WAIT_UNTIL = 'domcontentloaded'
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 配置 / 列表 / 文件名助手（独立实现，避免依赖原 netreptile.py）
# ---------------------------------------------------------------------------

def load_config(config_path):
    """加载并规范化 JSON 配置文件。

    支持键：timeout, selector, selector_type, selectors, title, baseurl,
           parallel, delay, wait_until, settle_timeout
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file {config_path}: {e}")
        raise

    valid_config = {}

    def _to_int(value, name):
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid {name} value in config: {value!r}, ignored")
            return None

    for key in ('timeout', 'parallel', 'delay', 'settle_timeout'):
        if key in config:
            v = _to_int(config[key], key)
            if v is not None:
                # 并发与延迟不允许出现无意义的负值
                if key in ('parallel', 'delay') and v < 0:
                    logger.warning(f"Invalid {key} in config: {config[key]}, ignored")
                    continue
                valid_config[key] = v

    if 'selector' in config:
        valid_config['selector'] = str(config['selector'])

    if 'selector_type' in config:
        st = str(config['selector_type']).lower()
        if st in ('css', 'xpath'):
            valid_config['selector_type'] = st
        else:
            logger.warning(f"Invalid selector_type in config: {config['selector_type']}, ignored")

    if 'selectors' in config and isinstance(config['selectors'], list):
        valid_config['selectors'] = config['selectors']

    if 'wait_until' in config:
        wu = str(config['wait_until']).lower()
        if wu in ('domcontentloaded', 'load', 'networkidle'):
            valid_config['wait_until'] = wu
        else:
            logger.warning(f"Invalid wait_until in config: {config['wait_until']}, ignored")

    if 'title' in config:
        valid_config['title'] = str(config['title'])

    if 'baseurl' in config:
        baseurl = str(config['baseurl']).strip()
        if baseurl and not baseurl.endswith('/'):
            baseurl += '/'
        valid_config['baseurl'] = baseurl

    logger.info(f"Loaded configuration from {config_path}")
    return valid_config


def load_url_list(list_file):
    """读取 URL 列表文件（支持空行 / # 注释 / <a href> 标签）。"""
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"List file not found: {list_file}")
        raise

    urls = []
    for line in lines:
        if line.startswith('#'):
            continue
        if '<a href' in line.lower():
            match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
            if match:
                urls.append(match.group(1))
            else:
                logger.warning(f"Could not extract URL from <a href> tag: {line}")
        else:
            urls.append(line)

    logger.info(f"Loaded {len(urls)} URLs from {list_file}")
    return urls


def get_first_line_of_list_file(list_file):
    """读取 list 文件第一个非空行。"""
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    return line
        return ""
    except Exception as e:
        logger.error(f"Error reading list file {list_file}: {e}")
        return ""


def get_title(config, list_file=None):
    """执行与原版一致的标题推导规则。"""
    title = config.get('title', '')
    if title and str(title).strip():
        return re.sub(r'[<>:"/\\|?*]', '', str(title).strip())

    if list_file:
        first_line = get_first_line_of_list_file(list_file)
        if first_line.startswith('#'):
            return re.sub(r'[<>:"/\\|?*]', '', first_line[1:].strip())
    return None


def generate_output_filename(config, list_file=None):
    title = get_title(config, list_file)
    if title:
        return f"{title}.txt"
    if list_file:
        return f"{Path(list_file).stem}.txt"
    return "output.txt"


def normalize_url(url, baseurl=None):
    """baseurl 拼接 + 缺失协议自动补 https://（与原版一致）。"""
    if baseurl and not url.startswith(('http://', 'https://', 'file://', '//')):
        if url.startswith('/') and baseurl.endswith('/'):
            url = url[1:]
        original = url
        url = baseurl + url
        logger.info(f"Applied baseurl to relative URL: {original} -> {url}")

    if not url.startswith(('http://', 'https://', 'file://')):
        logger.warning(f"URL doesn't start with http://, https:// or file://: {url}")
        url = f"https://{url}"

    return url


# ---------------------------------------------------------------------------
# 内容格式化
# ---------------------------------------------------------------------------

def format_content_with_timeout_markers(result):
    """content 在导航超时时加上醒目标记（与原版一致）。"""
    content = result.get('content', '')
    timeout_occurred = result.get('timeout_occurred', False)
    url = result.get('url', 'Unknown URL')

    if not timeout_occurred:
        return content

    marker = "=" * 80
    header = f"TIMEOUT OCCURRED - Content may be incomplete\nURL: {url}\n"
    footer = f"END OF TIMEOUT CONTENT - URL: {url}\n"
    return f"\n{marker}\n{header}{marker}\n\n{content}\n\n{marker}\n{footer}{marker}\n"


# ---------------------------------------------------------------------------
# 核心抓取
# ---------------------------------------------------------------------------

async def _extract_content(page, timeout, selector, selector_type, selectors):
    """页面上执行内容提取，返回值格式与原版等价但跳过无效内容筛选逻辑。"""
    if selectors:
        content = await process_selectors(page, selectors)
    elif selector:
        logger.info(f"Extracting text from containers matching selector: {selector} (type: {selector_type})")
        if selector_type == 'css':
            elements = await page.query_selector_all(selector)
        elif selector_type == 'xpath':
            elements = await page.query_selector_all(f'xpath={selector}')
        else:
            raise ValueError(f"Unsupported selector type: {selector_type}. Use 'css' or 'xpath'.")

        extracted = []
        for i, element in enumerate(elements, 1):
            try:
                text = (await element.text_content() or '').strip()
                if text:
                    extracted.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract text from element {i}: {e}")
        content = "\n".join(extracted)
    else:
        content = await page.content()

    return content if content else ""


async def _navigate(page, url, timeout, wait_until, settle_timeout):
    """
    导航到 URL。

    返回:
        bool: 是否发生导航超时
    """
    timeout_occurred = False
    try:
        await page.goto(url, wait_until=wait_until, timeout=timeout)
    except PlaywrightTimeoutError as e:  # 导航超时 -> 停止加载并沿用已加载内容
        print(f"Error Type: [{e.__class__.__name__}]")
        logger.warning(f"Navigation timeout occurred on {url}: {e}")
        logger.info("Stopping page loading and continuing with already loaded content...")
        timeout_occurred = True
        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass
    except Exception as e:  # 其它导航硬错误（DNS、拒绝连接、证书……）
        logger.error(f"Navigation error on {url}: [{e.__class__.__name__}] {e}")
        raise
    else:
        # wait_until=networkidle 已等待到空闲；其余情况给一个短宽限，
        # 让关键 XHR/懒加载有机会生效。超时不视为整体导航超时。
        if wait_until != 'networkidle' and settle_timeout > 0:
            try:
                await page.wait_for_load_state('networkidle', timeout=settle_timeout)
            except Exception:
                logger.info("Settle wait (networkidle grace) timed out, continuing...")
    return timeout_occurred


async def _fetch_page(browser, url, timeout, wait_until, settle_timeout,
                      selector, selector_type, selectors):
    """在共享 browser 的一个独立 context/page 内抓取并返回结果。"""
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=DEFAULT_USER_AGENT
    )
    page = await context.new_page()
    try:
        logger.info(f"Navigating to {url}")
        timeout_occurred = await _navigate(page, url, timeout, wait_until, settle_timeout)

        content = await _extract_content(page, timeout, selector, selector_type, selectors)

        if not content:
            logger.warning(f"No content extracted from {url}")
        return {"content": content, "timeout_occurred": timeout_occurred, "url": url}
    finally:
        await context.close()  # 关闭 context 即释放 page


async def fetch_page_content(url, timeout=DEFAULT_TIMEOUT, selector=None,
                             selector_type='css', wait_until=DEFAULT_WAIT_UNTIL,
                             settle_timeout=DEFAULT_SETTLE_TIMEOUT, selectors=None):
    """
    独立模式（单 URL）：自行启动并关闭浏览器后抓取。

    保持与原版签名兼容（新增 wait_until / settle_timeout 可选参数），
    fix_errors.py 若改为从本模块导入可无缝工作。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            return await _fetch_page(browser, url, timeout, wait_until,
                                     settle_timeout, selector, selector_type, selectors)
        finally:
            await browser.close()


async def fetch_page_content_with_selectors(url, timeout=DEFAULT_TIMEOUT,
                                            selectors=None, wait_until=DEFAULT_WAIT_UNTIL,
                                            settle_timeout=DEFAULT_SETTLE_TIMEOUT):
    """兼容模式：复杂 selectors 数组 + 独立浏览器。"""
    return await fetch_page_content(
        url, timeout=timeout, selectors=selectors,
        wait_until=wait_until, settle_timeout=settle_timeout
    )


# ---------------------------------------------------------------------------
# URL 级处理
# ---------------------------------------------------------------------------

async def process_one_url(browser, url, timeout, wait_until, settle_timeout,
                          selector, selector_type, selectors):
    """处理单个 URL；失败返回 None；注意 URL 需在调用前 normalize。"""
    try:
        return await _fetch_page(
            browser, url, timeout, wait_until, settle_timeout,
            selector, selector_type, selectors
        )
    except Exception as e:
        logger.error(f"Failed to process {url}: [{e.__class__.__name__}] {e}")
        return None


# ---------------------------------------------------------------------------
# 批处理：单浏览器 + 信号量并发 + 一次 IO
# ---------------------------------------------------------------------------

async def process_url_list(browser, urls, *, timeout, wait_until, settle_timeout,
                           selector, selector_type, baseurl, selectors,
                           parallel, delay_ms):
    """
    在共享浏览器上并发处理 URL 列表。

    返回:
        (results, stats, err_items)
        results: list[(index, original_url, normalized_url, result|None)]
        stats: dict(successful, warning, error)
        err_items: 需要写入 warning_error_url.log 的总明细 (已在内部记录两种)
    """
    # 限制并发度至少 1
    parallel = max(1, parallel)
    semaphore = asyncio.Semaphore(parallel)
    total = len(urls)
    completed = 0
    stats = {"successful": 0, "warning": 0, "error": 0}
    entries = []  # (index, uuid_str, url, kind)

    # 提前完成全部 URL 归一化（纯本地计算，不占用浏览器连接槽）
    normalized_urls = [normalize_url(raw, baseurl) for raw in urls]

    async def worker(i, raw_url, u):
        nonlocal completed
        async with semaphore:
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
            uuid4 = uuid.uuid4()
            result = await process_one_url(
                browser, u, timeout, wait_until, settle_timeout,
                selector, selector_type, selectors
            )
            completed += 1
            entry = (i, str(uuid4), raw_url)
            if result is None:
                stats["error"] += 1
                entries.append((*entry, "error"))
            elif result.get("timeout_occurred"):
                stats["warning"] += 1
                entries.append((*entry, "warning"))
            else:
                stats["successful"] += 1

            kind = "W/E" if result is None else ("W/E" if result.get("timeout_occurred") else "OK")
            # 简短进度
            print(f"[{i + 1}/{total}][{kind}] {raw_url}", flush=True)
            return i, raw_url, result

    task_results = await asyncio.gather(
        *(worker(i, raw, u) for i, (raw, u) in enumerate(zip(urls, normalized_urls)))
    )
    # 按原始顺序排列
    ordered = {}
    for t in task_results:
        if t is not None:
            ordered[t[0]] = t
    results = [ordered[i] for i in range(total) if i in ordered]
    return results, stats, entries


def build_output_content(title, results):
    """
    构造完整输出文件文本。results 必须已按 URL 索引升序。
    格式与新版目标一致：
      - 标题头
      - 成功/超时 URL 直接写入内容（超时自带标记）
      - 失败 URL 写入 ===== ERROR ==== 块
    """
    parts = [f"\n{title}\n\n"] if results else []
    prev_index = None

    for i, raw_url, result in results:
        if prev_index is not None:
            parts.append("\n" * 4)
        else:
            parts.append("")  # 首个 URL 无前导换行（等效原 lstrip 行为）

        if result is not None:
            parts.append(format_content_with_timeout_markers(result))
        else:
            parts.append(
                f"{'=' * 80}\nERROR - Failed to process URL: {raw_url}\n{'=' * 80}"
            )
        prev_index = i
    return "".join(parts)


# ---------------------------------------------------------------------------
# 主命令流程
# ---------------------------------------------------------------------------

def _write_warning_log(args_info, output_file, stats, entries, title):
    """出现 warning/error 时统一写入日志文件。"""
    try:
        with open("warning_error_url.log", 'a', encoding='utf-8') as logf:
            logf.write(f"\n\nDateTime: {datetime.now()}\n")
            logf.write(f"\t--config: {args_info.get('config')}\n")
            logf.write(f"\t--list: {args_info.get('list_file')}\n")
            logf.write(f"\toutput: {output_file}\n")
            logf.write(f"\ttitle: {title}\n")
            for k in ('successful', 'warning', 'error'):
                logf.write(f"\t{k}: {stats[k]}\n")

            max_line = int(max(len(entries) / 10, 50))
            for kind in ('warning', 'error'):
                if stats[kind] > 0:
                    logf.write(f"\n{kind.upper()} ({stats[kind]}):\n")
                    count = 0
                    shown = 0
                    for idx, uid, url, entry_kind in entries:
                        if entry_kind != kind:
                            continue
                        count += 1
                        if count <= max_line:
                            logf.write(f"{idx + 1}\t{uid}\t{url}\n")
                            shown += 1
                    if count > shown:
                        logf.write("...\n")
    except Exception as e:
        logger.error(f"Failed to write warning_error_url.log: {e}")


async def run_batch(args, params):
    """--list 批处理主流程。"""
    urls = load_url_list(args.list_file)
    if not urls:
        logger.error(f"No valid URLs found in {args.list_file}")
        sys.exit(1)

    total = len(urls)
    title = get_title(params.config, args.list_file)
    logger.info(f"Processing {total} URLs from {args.list_file} (parallel={params.parallel}, "
                f"wait_until={params.wait_until}, delay={params.delay_ms}ms)")

    # 一次性创建输出文件
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                results, stats, entries = await process_url_list(
                    browser, urls,
                    timeout=params.timeout,
                    wait_until=params.wait_until,
                    settle_timeout=params.settle_timeout,
                    selector=params.selector,
                    selector_type=params.selector_type,
                    baseurl=params.baseurl,
                    selectors=params.selectors,
                    parallel=params.parallel,
                    delay_ms=params.delay_ms,
                )
            finally:
                await browser.close()

        # 单次写入输出文件
        content = build_output_content(title, results)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        successful, warning, error = stats['successful'], stats['warning'], stats['error']
        print(f"\n{'=' * 60}")
        print(f"Finished {total} URLs: {successful} success, {warning} timeout-warning, {error} error.")
        print(f"Saved to: {args.output_file}")
        print(f"{'=' * 60}")

        # 日志只在出现 warning/error 时写入
        if warning > 0 or error > 0:
            _write_warning_log(
                {"config": args.config, "list_file": args.list_file},
                args.output_file, stats, entries, title
            )
            logger.warning(f"Warnings/Errors({warning}/{error}) occurred; details in warning_error_url.log")

        if successful == 0:
            logger.error("Failed to process any URLs from the list")
            sys.exit(1)
        if error > 0:
            logger.error("Some URLs failed to process.")
            sys.exit(1)
        return 0
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        sys.exit(1)


async def run_single(args, params):
    """单 URL 模式（原行为语义 + 新的 wait 策略）。"""
    raw_url = args.url
    final_url = normalize_url(raw_url, params.baseurl)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                result = await process_one_url(
                    browser, final_url, params.timeout, params.wait_until,
                    params.settle_timeout, params.selector, params.selector_type,
                    params.selectors
                )
            finally:
                await browser.close()

        if result is None:
            logger.error(f"Failed to process {final_url}")
            sys.exit(1)

        formatted = format_content_with_timeout_markers(result)

        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(formatted)

        if result.get('timeout_occurred'):
            logger.warning(f"Timeout occurred while processing {final_url} - content marked with timeout indicators")
        print(f"Successfully saved page content to: {args.output_file}")
        return 0
    except Exception as e:
        logger.error(f"Failed to process {final_url}: {e}")
        sys.exit(1)


async def main_entry(args, params):
    """主流程入口（供 asyncio.run 调用）。"""
    if args.list_file:
        await run_batch(args, params)
    else:
        await run_single(args, params)


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description='NetReptile-Fast: high-performance web content fetcher using Playwright '
                    '(reuses one browser across a URL batch, with concurrency control)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python netreptile_fast.py <url> <output_file>
  python netreptile_fast.py https://example.com output.html
  python netreptile_fast.py --list urls.txt output.txt --config config/6park.json
  python netreptile_fast.py --list urls.txt --config config.json --parallel 5
  python netreptile_fast.py --list urls.txt out.txt --wait-until networkidle --parallel 1
        """
    )

    parser.add_argument('url', nargs='?', help='URL of the web page to fetch (ignored with --list)')
    parser.add_argument('output_file', nargs='?',
                        help='Path to the output file. If omitted, auto-generated from config title or list file.')

    parser.add_argument('--config', help='Path to JSON configuration file')
    parser.add_argument('--timeout', type=int, default=None,
                        help='Navigation timeout in milliseconds (overrides config)')
    parser.add_argument('--selector', help='CSS selector or XPath (overrides config)')
    parser.add_argument('--selector-type', choices=['css', 'xpath'], default=None,
                        help='Selector type: css or xpath')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')

    # --- 新增性能相关参数 ---
    parser.add_argument('--list', dest='list_file',
                        help='Path to a file containing a list of URLs (one per line)')
    parser.add_argument('--parallel', type=int, default=None,
                        help=f'Number of pages loaded concurrently in batch mode '
                             f'(default: config "parallel" or {DEFAULT_PARALLEL})')
    parser.add_argument('--delay', type=int, default=None,
                        help='Polite delay in milliseconds between each URL start (default 0)')
    parser.add_argument('--wait-until', choices=['domcontentloaded', 'load', 'networkidle'],
                        default=None,
                        help=f'Wait strategy for page navigation '
                             f'(default: config "wait_until" or {DEFAULT_WAIT_UNTIL})')
    parser.add_argument('--settle-timeout', type=int, default=None,
                        help=f'After domcontentloaded/load, wait up to this many ms for networkidle '
                             f'(default: config "settle_timeout" or {DEFAULT_SETTLE_TIMEOUT})')
    return parser


class ParamBundle:
    """融合 CLI 参数与 config 之后的最终运行参数。"""
    __slots__ = ('config', 'timeout', 'selector', 'selector_type', 'baseurl',
                 'selectors', 'parallel', 'delay_ms', 'wait_until', 'settle_timeout')


def resolve_params(args):
    config = {}
    if args.config:
        config = load_config(args.config)
        logger.info(f"Configuration loaded: {config}")

    params = ParamBundle()
    params.config = config
    params.timeout = args.timeout if args.timeout is not None else config.get('timeout', DEFAULT_TIMEOUT)
    params.selector = args.selector if args.selector is not None else config.get('selector')
    params.selector_type = args.selector_type if args.selector_type is not None else config.get('selector_type', 'css')
    params.baseurl = config.get('baseurl')
    params.selectors = config.get('selectors')

    # 命令行 selector 优先于复杂 selectors（与原版一致）
    if args.selector is not None:
        params.selectors = None

    params.parallel = args.parallel if args.parallel is not None else config.get('parallel', DEFAULT_PARALLEL)
    params.delay_ms = args.delay if args.delay is not None else config.get('delay', 0)
    params.wait_until = (args.wait_until if args.wait_until is not None
                         else config.get('wait_until', DEFAULT_WAIT_UNTIL))
    params.settle_timeout = (args.settle_timeout if args.settle_timeout is not None
                             else config.get('settle_timeout', DEFAULT_SETTLE_TIMEOUT))

    logger.debug(f"Final params - timeout: {params.timeout}, selector: {params.selector}, "
                 f"selector_type: {params.selector_type}, baseurl: {params.baseurl}, "
                 f"selectors: {params.selectors}, parallel: {params.parallel}, "
                 f"delay_ms: {params.delay_ms}, wait_until: {params.wait_until}, "
                 f"settle_timeout: {params.settle_timeout}")
    return params


def main():
    parser = build_parser()
    args = parser.parse_args()

    # 修复 --list 位置参数错位问题（与原版相同）
    if args.list_file and args.output_file is None and args.url is not None:
        args.output_file = args.url
        args.url = None
        logger.debug(f"Fixed argument parsing: moved '{args.output_file}' from url to output_file")

    if not args.list_file and not args.url:
        parser.error("Either a URL or --list option must be provided")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    params = resolve_params(args)

    # 输出文件名推导
    if args.output_file is None:
        args.output_file = generate_output_filename(config=params.config, list_file=args.list_file)
        logger.info(f"Generated output filename: {args.output_file}")
        print(f"Output filename not specified, using generated name: {args.output_file}")

    # Windows 事件循环：Playwright 在 Windows 上建议使用 Proactor
    # （Python <3.8 尤其需要）；asyncio.run 会基于该 policy 创建循环。
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        # asyncio.run() 在 Python 3.7+ 自动创建/关闭事件循环并清理任务，
        # 避免手动管理遗留 loop 引发的 DeprecationWarning。
        asyncio.run(main_entry(args, params))
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except SystemExit:
        raise  # run_batch/run_single 内 sys.exit() 的状态码原样透传
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()