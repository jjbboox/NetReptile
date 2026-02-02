#!/usr/bin/env python3
"""
修复程序 - 修复已生成的.txt文件中的错误

用法:
    python fix_errors.py <input_file> [--config <config_file>] [--output <output_file>]

示例:
    python fix_errors.py temp/透视之眼.txt --config config/quanben.json
    python fix_errors.py temp/透视之眼.txt --config config/quanben.json --output fixed_透视之眼.txt
"""

import asyncio
import sys
import re
import argparse
import json
from pathlib import Path
import logging
from typing import Optional, Dict, Any

# 导入netreptile中的函数
from netreptile import (
    fetch_page_content_with_selectors,
    fetch_page_content,
    load_config,
    format_content_with_timeout_markers
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_error_blocks(content: str):
    """
    从内容中提取所有错误块。
    
    错误块格式:
    ================================================================================
    ERROR - Failed to process URL: <url>
    ================================================================================
    
    返回:
        list: 包含 (start_index, end_index, url) 的元组列表
    """
    pattern = r'={80}\s*\nERROR - Failed to process URL: (.+?)\s*\n={80}'
    matches = list(re.finditer(pattern, content, re.DOTALL))
    
    blocks = []
    for match in matches:
        start = match.start()
        end = match.end()
        url = match.group(1).strip()
        blocks.append((start, end, url))
    
    logger.info(f"找到 {len(blocks)} 个错误块")
    return blocks


async def fetch_url_content(url: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    使用配置爬取URL内容。
    
    参数:
        url: 要爬取的URL
        config: 配置字典
        
    返回:
        dict: 包含内容、超时状态和URL的字典，如果失败则返回None
    """
    # 从配置中获取参数
    timeout = config.get('timeout', 30000)
    selector = config.get('selector')
    selector_type = config.get('selector_type', 'css')
    baseurl = config.get('baseurl')
    selectors = config.get('selectors')
    
    # 应用baseurl（如果提供且URL是相对的）
    if baseurl and not url.startswith(('http://', 'https://', 'file://', '//')):
        # 检查URL是否以斜杠开头（相对于baseurl的绝对路径）
        if url.startswith('/'):
            # 如果baseurl以斜杠结尾，则从URL中移除前导斜杠
            if baseurl.endswith('/'):
                url = url[1:]
        # 拼接baseurl和URL
        original_url = url
        url = baseurl + url
        logger.info(f"应用baseurl到相对URL: {original_url} -> {url}")
    
    # 验证和规范化URL
    if not url.startswith(('http://', 'https://', 'file://')):
        logger.warning(f"URL不以http://、https://或file://开头: {url}")
        # 尝试添加https://（如果缺失）
        url = f"https://{url}"
        logger.info(f"尝试: {url}")
    
    try:
        # 如果有选择器数组，使用复杂选择器，否则使用简单选择器
        if selectors:
            result = await fetch_page_content_with_selectors(
                url, 
                timeout, 
                selectors=selectors
            )
        else:
            result = await fetch_page_content(
                url, 
                timeout, 
                selector=selector,
                selector_type=selector_type
            )
        return result
    except Exception as e:
        logger.error(f"爬取 {url} 失败: {e}")
        return None


def replace_error_block(content: str, start: int, end: int, new_content: str) -> str:
    """
    用新内容替换错误块。
    
    参数:
        content: 原始内容
        start: 错误块开始索引
        end: 错误块结束索引
        new_content: 要插入的新内容
        
    返回:
        str: 替换后的内容
    """
    return content[:start] + new_content + content[end:]


async def process_file(input_file: str, config_file: Optional[str] = None, output_file: Optional[str] = None):
    """
    处理输入文件，修复错误块。
    
    参数:
        input_file: 输入文件路径
        config_file: 配置文件路径（可选）
        output_file: 输出文件路径（可选）
    """
    # 读取输入文件
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"读取输入文件失败 {input_file}: {e}")
        sys.exit(1)
    
    # 加载配置（如果提供）
    config = {}
    if config_file:
        try:
            config = load_config(config_file)
            logger.info(f"配置已加载: {config}")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            sys.exit(1)
    
    # 提取错误块
    error_blocks = extract_error_blocks(content)
    if not error_blocks:
        logger.info("未找到错误块，无需修复")
        return
    
    # 处理每个错误块
    fixed_content = content
    # 需要跟踪偏移量，因为替换会改变字符串长度
    offset = 0
    fix_success_count = 0
    fix_error_count = 0
    for i, (start, end, url) in enumerate(error_blocks, 1):
        logger.info(f"处理错误块 {i}/{len(error_blocks)}: {url}")
        
        # 调整索引以考虑之前的替换
        adjusted_start = start + offset
        adjusted_end = end + offset
        
        # 爬取URL
        result = await fetch_url_content(url, config)
        
        if result is not None:
            # 格式化内容（如果需要超时标记）
            new_content = format_content_with_timeout_markers(result)
            
            # 替换错误块
            fixed_content = replace_error_block(
                fixed_content, 
                adjusted_start, 
                adjusted_end, 
                new_content
            )
            
            # 更新偏移量
            old_length = adjusted_end - adjusted_start
            new_length = len(new_content)
            offset += new_length - old_length
            fix_success_count += 1
            logger.info(f"[{i}/{error_blocks}]成功替换错误块 [S/E:{fix_success_count}/{fix_error_count}]")
        else:
            fix_error_count += 1
            logger.warning(f"[{i}/{error_blocks}]爬取失败，跳过错误块 {fix_error_count}: {url}")
    
    # 确定输出文件路径
    if output_file is None:
        # 如果没有指定输出文件，创建带_fixed后缀的文件
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_fixed{input_path.suffix}"
    
    # 写入输出文件
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        
        logger.info(f"修复后的内容已保存到 {output_file}")
        print(f"修复完成！输出文件: {output_file}")
        
    except Exception as e:
        logger.error(f"保存输出文件失败 {output_file}: {e}")
        sys.exit(1)


async def main_async(args):
    """主异步函数"""
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("详细模式已启用")
    
    # 处理文件
    await process_file(
        input_file=args.input_file,
        config_file=args.config,
        output_file=args.output
    )


def main():
    """主入口点"""
    parser = argparse.ArgumentParser(
        description='修复已生成的.txt文件中的错误',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s temp/透视之眼.txt --config config/quanben.json
  %(prog)s temp/透视之眼.txt --config config/quanben.json --output fixed_透视之眼.txt
        """
    )
    
    parser.add_argument(
        'input_file',
        help='包含错误块的输入文件路径'
    )
    
    parser.add_argument(
        '--config',
        help='JSON配置文件路径（包含timeout、selector、selector_type、baseurl、selectors）'
    )
    
    parser.add_argument(
        '--output',
        help='输出文件路径。如果未指定，将创建带_fixed后缀的文件'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='启用详细日志'
    )
    
    # 解析参数
    args = parser.parse_args()
    
    # 处理Windows特定的asyncio问题
    if sys.platform == 'win32':
        # 尝试使用ProactorEventLoop以获得更好的Windows兼容性
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = None
    try:
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 运行主异步函数
        loop.run_until_complete(main_async(args))
        
    except KeyboardInterrupt:
        logger.info("操作被用户取消")
        sys.exit(130)
    except Exception as e:
        logger.error(f"意外错误: {e}")
        sys.exit(1)
    finally:
        # 清理事件循环
        if loop:
            try:
                # 取消所有运行中的任务
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()
                
                # 运行循环直到所有任务被取消
                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                
                # 关闭异步生成器
                loop.run_until_complete(loop.shutdown_asyncgens())
                
                # 关闭循环
                loop.close()
            except Exception:
                pass  # 忽略清理期间的错误


if __name__ == "__main__":
    main()
