#!/usr/bin/env python3
"""
Get Images from URL - Windows GUI Program
图形界面版 getimgfromurl.py，支持单URL和批量模式，以及登录认证功能。

Usage:
    python getimgfromurl_gui.py
"""

import sys
import os
import re
import json
import logging
import threading
import asyncio
import io
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Dict, Any, List, Tuple

# 添加上级目录到路径，以便导入 getimgfromurl 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ============================================================
# 日志重定向 - 将日志输出到 GUI 文本框
# ============================================================
class TextHandler(logging.Handler):
    """将日志输出重定向到 tkinter Text 控件"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        # 设置日志格式
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        # 设置日志级别
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        msg = self.format(record)
        # 使用 after 确保线程安全
        def append():
            self.text_widget.configure(state='normal')
            # 根据日志级别设置颜色
            tag = record.levelname.lower()
            if tag == 'error':
                self.text_widget.insert(END, msg + '\n', 'error')
            elif tag == 'warning':
                self.text_widget.insert(END, msg + '\n', 'warning')
            else:
                self.text_widget.insert(END, msg + '\n', 'info')
            self.text_widget.see(END)
            self.text_widget.configure(state='disabled')
        self.text_widget.after(0, append)


class StdoutRedirector:
    """将 print 输出重定向到 tkinter Text 控件"""
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        if message.strip():
            def append():
                self.text_widget.configure(state='normal')
                self.text_widget.insert(END, message, 'stdout')
                self.text_widget.see(END)
                self.text_widget.configure(state='disabled')
            self.text_widget.after(0, append)

    def flush(self):
        pass


# ============================================================
# 主 GUI 应用程序
# ============================================================
class GetImagesFromUrlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Get Images from URL - 图片提取工具")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use('vista' if 'vista' in self.style.theme_names() else 'clam')

        # 运行状态
        self.is_running = False
        self.cancel_flag = False

        # 创建界面
        self._create_widgets()

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ============================================================
    # 界面构建
    # ============================================================
    def _create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        # ========== 标签页切换 (单URL / 批量) ==========
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=BOTH, expand=True, pady=(0, 5))

        # ---- 标签页1: 单 URL 模式 ----
        single_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(single_tab, text="  单 URL 模式  ")

        # URL
        url_row = ttk.Frame(single_tab)
        url_row.pack(fill=X, pady=5)
        ttk.Label(url_row, text="URL:", width=10).pack(side=LEFT)
        self.url_entry = ttk.Entry(url_row)
        self.url_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))

        # 输出目录
        out_row = ttk.Frame(single_tab)
        out_row.pack(fill=X, pady=5)
        ttk.Label(out_row, text="输出目录:", width=10).pack(side=LEFT)
        self.out_dir_entry = ttk.Entry(out_row)
        self.out_dir_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        ttk.Button(out_row, text="浏览...", width=8,
                   command=self._browse_output_dir).pack(side=LEFT)

        # ---- 标签页2: 批量模式 (默认选中) ----
        batch_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(batch_tab, text="  批量模式  ")
        # 默认选中批量模式标签页
        self.notebook.select(1)

        # ========== 认证设置 (放在URL列表上方) ==========
        auth_frame = ttk.LabelFrame(batch_tab, text="认证设置", padding="5")
        auth_frame.pack(fill=X, pady=(0, 5))

        auth_row1 = ttk.Frame(auth_frame)
        auth_row1.pack(fill=X, pady=2)
        self.auth_enabled = BooleanVar(value=False)
        ttk.Checkbutton(auth_row1, text="启用登录认证",
                        variable=self.auth_enabled,
                        command=self._on_auth_toggle).pack(side=LEFT)
        ttk.Label(auth_row1, text="认证文件:").pack(side=LEFT, padx=(15, 5))
        self.auth_file_entry = ttk.Entry(auth_row1, state='disabled')
        self.auth_file_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        self.auth_browse_btn = ttk.Button(auth_row1, text="浏览...", width=8,
                                          state='disabled',
                                          command=self._browse_auth_file)
        self.auth_browse_btn.pack(side=LEFT)

        # 认证配置预览
        auth_preview_frame = ttk.LabelFrame(auth_frame, text="认证配置预览", padding="2")
        auth_preview_frame.pack(fill=X, pady=2)
        self.auth_preview = scrolledtext.ScrolledText(
            auth_preview_frame, height=2, wrap=NONE,
            font=('Consolas', 9), state='disabled', bg='#f5f5f5')
        self.auth_preview.pack(fill=X)

        # ========== 指定输出目录 ==========
        output_frame = ttk.LabelFrame(batch_tab, text="指定输出目录（可选，留空则使用列表中每行指定的目录）", padding="5")
        output_frame.pack(fill=X, pady=(0, 5))

        output_row = ttk.Frame(output_frame)
        output_row.pack(fill=X, pady=2)
        ttk.Label(output_row, text="输出目录:", width=10).pack(side=LEFT)
        self.batch_output_entry = ttk.Entry(output_row)
        self.batch_output_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        ttk.Button(output_row, text="浏览...", width=8,
                   command=self._browse_batch_output_dir).pack(side=LEFT)

        # ========== URL 列表编辑区 ==========
        edit_frame = ttk.LabelFrame(batch_tab, text="URL 列表（每行格式: URL 输出目录，可直接编辑）", padding="2")
        edit_frame.pack(fill=BOTH, expand=True, pady=(0, 2))
        self.list_editor = scrolledtext.ScrolledText(
            edit_frame, wrap=NONE, height=5,
            font=('Consolas', 9), bg='#ffffff')
        self.list_editor.pack(fill=BOTH, expand=True)
        # 插入提示文本
        self.list_editor.insert('1.0', "# 每行一个任务，格式: URL 输出目录\n# 例如:\n# https://example.com/page1 ./output1\n# https://example.com/page2 ./output2\n")

        # ========== 文本搜索替换组件 ==========
        replace_frame = ttk.Frame(batch_tab)
        replace_frame.pack(fill=X, pady=(0, 5))
        
        ttk.Label(replace_frame, text="查找:").pack(side=LEFT)
        self.search_entry = ttk.Entry(replace_frame, width=20)
        self.search_entry.pack(side=LEFT, padx=(5, 10))
        
        ttk.Label(replace_frame, text="替换为:").pack(side=LEFT)
        self.replace_entry = ttk.Entry(replace_frame, width=20)
        self.replace_entry.pack(side=LEFT, padx=(5, 5))
        
        ttk.Button(replace_frame, text="替换全部",
                   command=self._do_replace_all).pack(side=LEFT, padx=(10, 0))

        # 基础URL + 并行数
        batch_row = ttk.Frame(batch_tab)
        batch_row.pack(fill=X, pady=5)
        ttk.Label(batch_row, text="基础URL:", width=10).pack(side=LEFT)
        self.base_url_entry = ttk.Entry(batch_row)
        self.base_url_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        ttk.Label(batch_row, text="并行任务数:").pack(side=LEFT)
        self.parallel_spin = ttk.Spinbox(batch_row, from_=1, to=10, width=5)
        self.parallel_spin.set(3)
        self.parallel_spin.pack(side=LEFT, padx=(5, 0))

        # ========== 高级设置 (可折叠) ==========
        self.adv_expanded = BooleanVar(value=False)
        adv_header = ttk.Frame(main_frame)
        adv_header.pack(fill=X, pady=(0, 2))
        self.adv_toggle_btn = ttk.Button(adv_header, text="▶ 高级设置",
                                         command=self._toggle_advanced)
        self.adv_toggle_btn.pack(side=LEFT)

        self.adv_frame = ttk.LabelFrame(main_frame, padding="5")
        # 默认隐藏

        # 超时
        adv_row1 = ttk.Frame(self.adv_frame)
        adv_row1.pack(fill=X, pady=2)
        ttk.Label(adv_row1, text="超时(ms):", width=10).pack(side=LEFT)
        self.timeout_entry = ttk.Entry(adv_row1, width=12)
        self.timeout_entry.insert(0, "30000")
        self.timeout_entry.pack(side=LEFT, padx=(0, 20))
        ttk.Label(adv_row1, text="图片扩展名:").pack(side=LEFT)
        self.ext_combo = ttk.Combobox(adv_row1, values=['jpg', 'png', 'gif', 'bmp', 'webp'], width=8)
        self.ext_combo.set('jpg')
        self.ext_combo.pack(side=LEFT, padx=(5, 0))

        # User-Agent
        adv_row2 = ttk.Frame(self.adv_frame)
        adv_row2.pack(fill=X, pady=2)
        ttk.Label(adv_row2, text="User-Agent:", width=10).pack(side=LEFT)
        self.ua_entry = ttk.Entry(adv_row2)
        self.ua_entry.pack(side=LEFT, fill=X, expand=True)

        # 代理
        adv_row3 = ttk.Frame(self.adv_frame)
        adv_row3.pack(fill=X, pady=2)
        ttk.Label(adv_row3, text="代理:", width=10).pack(side=LEFT)
        self.proxy_entry = ttk.Entry(adv_row3)
        self.proxy_entry.pack(side=LEFT, fill=X, expand=True)

        # 详细日志
        adv_row4 = ttk.Frame(self.adv_frame)
        adv_row4.pack(fill=X, pady=2)
        self.verbose_var = BooleanVar(value=False)
        ttk.Checkbutton(adv_row4, text="启用详细日志 (Verbose)",
                        variable=self.verbose_var).pack(side=LEFT)

        # ========== 操作按钮 ==========
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=(5, 5))

        self.start_btn = ttk.Button(btn_frame, text="▶ 开始提取",
                                    command=self._start_extraction)
        self.start_btn.pack(side=LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(btn_frame, text="■ 停止",
                                   command=self._stop_extraction, state='disabled')
        self.stop_btn.pack(side=LEFT)

        # 清空日志按钮
        ttk.Button(btn_frame, text="清空日志",
                   command=self._clear_log).pack(side=RIGHT)

        # ========== 日志输出区域 (固定在底部，高度缩小) ==========
        log_frame = ttk.LabelFrame(main_frame, text="日志输出", padding="2")
        log_frame.pack(fill=X, side=BOTTOM, pady=(0, 5))
        # 固定高度约 8 行
        log_frame.configure(height=160)
        log_frame.pack_propagate(False)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=WORD, state='disabled',
            font=('Consolas', 9), height=6)
        self.log_text.pack(fill=BOTH, expand=True)

        # 配置日志文本标签样式
        self.log_text.tag_config('info', foreground='#000000')
        self.log_text.tag_config('warning', foreground='#CC6600')
        self.log_text.tag_config('error', foreground='#CC0000')
        self.log_text.tag_config('stdout', foreground='#006600')
        self.log_text.tag_config('success', foreground='#006600', font=('Consolas', 9, 'bold'))

        # ========== 状态栏 ==========
        status_frame = ttk.Frame(main_frame, relief=SUNKEN, borderwidth=1)
        status_frame.pack(fill=X, side=BOTTOM)

        self.status_label = ttk.Label(status_frame, text="就绪", padding=(5, 2))
        self.status_label.pack(side=LEFT)

        self.stats_label = ttk.Label(status_frame, text="", padding=(5, 2))
        self.stats_label.pack(side=RIGHT)

        # 设置日志重定向
        self._setup_logging()

    def _setup_logging(self):
        """设置日志重定向到 GUI"""
        # 添加 TextHandler
        text_handler = TextHandler(self.log_text)
        root_logger = logging.getLogger()
        root_logger.addHandler(text_handler)
        root_logger.setLevel(logging.DEBUG)

        # 重定向 stdout
        sys.stdout = StdoutRedirector(self.log_text)

    # ============================================================
    # 事件处理
    # ============================================================
    def _on_auth_toggle(self):
        """认证开关切换"""
        state = 'normal' if self.auth_enabled.get() else 'disabled'
        self.auth_file_entry.configure(state=state)
        self.auth_browse_btn.configure(state=state)
        if not self.auth_enabled.get():
            self.auth_preview.configure(state='normal')
            self.auth_preview.delete('1.0', END)
            self.auth_preview.configure(state='disabled')

    def _toggle_advanced(self):
        """展开/折叠高级设置"""
        if self.adv_expanded.get():
            # 折叠
            self.adv_frame.pack_forget()
            self.adv_toggle_btn.configure(text="▶ 高级设置")
            self.adv_expanded.set(False)
        else:
            # 展开
            self.adv_frame.pack(fill=X, pady=(0, 5), after=self.adv_toggle_btn.master)
            self.adv_toggle_btn.configure(text="▼ 高级设置")
            self.adv_expanded.set(True)

    def _browse_output_dir(self):
        """浏览输出目录 (单URL模式)"""
        dir_path = filedialog.askdirectory(title="选择输出目录")
        if dir_path:
            self.out_dir_entry.delete(0, END)
            self.out_dir_entry.insert(0, dir_path)

    def _browse_batch_output_dir(self):
        """浏览输出目录 (批量模式)"""
        dir_path = filedialog.askdirectory(title="选择输出目录")
        if dir_path:
            self.batch_output_entry.delete(0, END)
            self.batch_output_entry.insert(0, dir_path)

    def _browse_list_file(self):
        """浏览列表文件，将内容导入到可编辑的列表编辑器中"""
        file_path = filedialog.askopenfilename(
            title="选择列表文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if file_path:
            self.list_file_entry.delete(0, END)
            self.list_file_entry.insert(0, file_path)
            self._import_list_file(file_path)

    def _import_list_file(self, file_path):
        """将列表文件内容导入到编辑器中"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.list_editor.delete('1.0', END)
            self.list_editor.insert('1.0', content)
            self._log_message(f"已导入列表文件: {file_path}", 'info')
        except Exception as e:
            self._log_message(f"读取列表文件失败: {e}", 'error')

    def _browse_auth_file(self):
        """浏览认证文件"""
        file_path = filedialog.askopenfilename(
            title="选择认证文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if file_path:
            self.auth_file_entry.delete(0, END)
            self.auth_file_entry.insert(0, file_path)
            self._preview_auth_file(file_path)

    def _preview_auth_file(self, file_path):
        """预览认证文件内容，并将 base_url 自动填入基础URL字段"""
        try:
            # 使用 getimgfromurl 的解析函数
            from getimgfromurl import parse_auth_file
            auth_config = parse_auth_file(file_path)

            self.auth_preview.configure(state='normal')
            self.auth_preview.delete('1.0', END)

            preview_lines = []
            if auth_config.get('base_url'):
                preview_lines.append(f"登录地址: {auth_config['base_url']}")
                # 自动将 base_url 填入基础URL字段
                self.base_url_entry.delete(0, END)
                self.base_url_entry.insert(0, auth_config['base_url'])
                self._log_message(f"已自动填入基础URL: {auth_config['base_url']}", 'info')
            if auth_config.get('user_name', {}).get('selector'):
                preview_lines.append(f"用户名选择器: {auth_config['user_name']['selector']}")
            if auth_config.get('password', {}).get('selector'):
                preview_lines.append(f"密码选择器: {auth_config['password']['selector']}")
            if auth_config.get('login_button', {}).get('selector'):
                preview_lines.append(f"登录按钮选择器: {auth_config['login_button']['selector']}")
            if auth_config.get('wait'):
                preview_lines.append(f"登录后等待: {auth_config['wait']}ms")

            self.auth_preview.insert('1.0', '\n'.join(preview_lines))
            self.auth_preview.configure(state='disabled')
        except Exception as e:
            self.auth_preview.configure(state='normal')
            self.auth_preview.delete('1.0', END)
            self.auth_preview.insert('1.0', f"解析认证文件失败: {e}")
            self.auth_preview.configure(state='disabled')

    def _do_replace_all(self):
        """在 URL 列表编辑器中进行文本搜索替换"""
        search_text = self.search_entry.get()
        replace_text = self.replace_entry.get()
        
        if not search_text:
            messagebox.showinfo("提示", "请输入要查找的文本")
            return
        
        # 获取编辑器当前内容
        content = self.list_editor.get('1.0', END)
        
        # 执行替换
        new_content = content.replace(search_text, replace_text)
        
        if new_content == content:
            self._log_message(f"未找到匹配的文本: '{search_text}'", 'warning')
            return
        
        # 更新编辑器内容
        self.list_editor.delete('1.0', END)
        self.list_editor.insert('1.0', new_content)
        
        # 计算替换次数
        count = content.count(search_text)
        self._log_message(f"替换完成: '{search_text}' -> '{replace_text}' (共 {count} 处)", 'success')

    def _log_message(self, message, level='info'):
        """记录日志到 GUI"""
        def append():
            self.log_text.configure(state='normal')
            self.log_text.insert(END, message + '\n', level)
            self.log_text.see(END)
            self.log_text.configure(state='disabled')
        self.log_text.after(0, append)

    def _clear_log(self):
        """清空日志"""
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', END)
        self.log_text.configure(state='disabled')

    def _update_status(self, text, stats_text=""):
        """更新状态栏"""
        def update():
            self.status_label.configure(text=text)
            self.stats_label.configure(text=stats_text)
        self.root.after(0, update)

    # ============================================================
    # 提取逻辑
    # ============================================================
    def _get_current_mode(self) -> str:
        """获取当前标签页对应的模式"""
        current_tab = self.notebook.index(self.notebook.select())
        return 'single' if current_tab == 0 else 'batch'

    def _parse_editor_tasks(self) -> List[Tuple[str, str]]:
        """从编辑器内容中解析任务列表
        
        支持格式:
        1. <a href="url">link_text</a> output_dir  - 提取href作为URL，link_text作为输出目录(如果后面没有指定)
        2. URL output_dir  - 标准格式
        
        Returns:
            List of tuples (url, output_dir)
        """
        content = self.list_editor.get('1.0', END).strip()
        tasks = []
        base_url = self.base_url_entry.get().strip() or None
        
        for line in content.split('\n'):
            line = line.strip()
            # 跳过空行和注释行
            if not line or line.startswith('#'):
                continue
            
            # 检查是否包含 <a href> 标签
            if '<a href=' in line.lower() or '<a href =' in line.lower():
                # 提取 href 中的 URL 和链接文本
                match = re.search(r'<a\s+href\s*=\s*["\']([^"\']+)["\'][^>]*>([^<]+)</a>', line, re.IGNORECASE)
                if match:
                    extracted_url = match.group(1)
                    link_text = match.group(2).strip()
                    
                    # 提取输出目录（标签后面的文本）
                    tag_pattern = r'<a\s+href\s*=\s*["\'][^"\']+["\'][^>]*>[^<]+</a>'
                    line_without_tag = re.sub(tag_pattern, '', line, flags=re.IGNORECASE).strip()
                    
                    if line_without_tag:
                        output_dir = line_without_tag
                    else:
                        # 如果没有指定输出目录，使用链接文本
                        output_dir = link_text
                    
                    # 如果提供了 base_url 且提取的 URL 是相对路径，进行拼接
                    if base_url and not extracted_url.startswith(('http://', 'https://', 'data:')):
                        from urllib.parse import urljoin
                        extracted_url = urljoin(base_url, extracted_url)
                    
                    tasks.append((extracted_url, output_dir))
                    continue
                else:
                    self._log_message(f"无法解析 <a href> 标签: {line}", 'warning')
                    continue
            
            # 标准格式: URL 输出目录
            parts = line.split(None, 1)  # 只分割第一个空格
            if len(parts) >= 2:
                url = parts[0]
                output_dir = parts[1]
                tasks.append((url, output_dir))
            else:
                self._log_message(f"跳过无效行: {line}", 'warning')
        
        return tasks

    def _start_extraction(self):
        """开始提取"""
        if self.is_running:
            return

        # 验证输入
        mode = self._get_current_mode()
        if mode == 'single':
            url = self.url_entry.get().strip()
            output_dir = self.out_dir_entry.get().strip()
            if not url:
                messagebox.showerror("错误", "请输入 URL")
                return
            if not output_dir:
                messagebox.showerror("错误", "请选择输出目录")
                return
        else:
            # 从编辑器获取内容
            tasks = self._parse_editor_tasks()
            if not tasks:
                messagebox.showerror("错误", "URL 列表为空，请导入列表文件或手动输入任务")
                return

        # 切换状态
        self.is_running = True
        self.cancel_flag = False
        self.start_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')

        # 清空旧日志
        self._clear_log()

        # 在后台线程中运行
        thread = threading.Thread(target=self._run_extraction, daemon=True)
        thread.start()

    def _stop_extraction(self):
        """停止提取"""
        self.cancel_flag = True
        self._log_message("用户请求停止...", 'warning')

    def _run_extraction(self):
        """在后台线程中运行提取"""
        try:
            mode = self._get_current_mode()

            # 收集公共参数
            timeout = int(self.timeout_entry.get() or "30000")
            ext = self.ext_combo.get() or "jpg"
            user_agent = self.ua_entry.get().strip() or None
            proxy = self.proxy_entry.get().strip() or None
            verbose = self.verbose_var.get()

            # 认证文件
            auth_file = None
            if self.auth_enabled.get():
                auth_file = self.auth_file_entry.get().strip() or None

            if mode == 'single':
                url = self.url_entry.get().strip()
                output_dir = self.out_dir_entry.get().strip()
                self._run_single(url, output_dir, timeout, user_agent, proxy, ext, verbose, auth_file)
            else:
                # 从编辑器解析任务列表
                tasks = self._parse_editor_tasks()
                base_url = self.base_url_entry.get().strip() or None
                parallel = int(self.parallel_spin.get() or "3")
                # 获取指定的输出目录（如果设置了，覆盖列表中每行的输出目录）
                batch_output_dir = self.batch_output_entry.get().strip() or None
                self._run_batch(tasks, base_url, timeout, user_agent, proxy, ext, verbose, parallel, auth_file, batch_output_dir)

        except Exception as e:
            self._log_message(f"发生错误: {e}", 'error')
            import traceback
            self._log_message(traceback.format_exc(), 'error')
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.start_btn.configure(state='normal'))
            self.root.after(0, lambda: self.stop_btn.configure(state='disabled'))
            if not self.cancel_flag:
                self._update_status("✅ 处理完成")
            else:
                self._update_status("⏹ 已停止")

    def _run_single(self, url, output_dir, timeout, user_agent, proxy, ext, verbose, auth_file):
        """运行单 URL 模式"""
        self._update_status("🔄 正在处理...")

        async def task():
            from getimgfromurl import process_single_task
            stats = await process_single_task(
                url=url,
                output_dir=output_dir,
                timeout=timeout,
                user_agent=user_agent,
                proxy=proxy,
                ext=ext,
                verbose=verbose,
                auth_file=auth_file
            )
            return stats

        try:
            stats = asyncio.run(task())
            self._show_single_result(stats)
        except Exception as e:
            if not self.cancel_flag:
                self._log_message(f"处理失败: {e}", 'error')

    def _run_batch(self, tasks: List[Tuple[str, str]], base_url, timeout, user_agent, proxy, ext, verbose, parallel, auth_file, batch_output_dir=None):
        """运行批量模式
        
        Args:
            tasks: 任务列表，每个元素为 (url, output_dir)
            batch_output_dir: 指定的输出目录，如果设置则在该目录下为每个任务创建子目录
        """
        self._update_status("🔄 正在处理批量任务...")

        async def run():
            from getimgfromurl import process_batch_tasks

            # 处理基础URL和输出目录
            processed_tasks = []
            for url, output_dir in tasks:
                # 如果指定了统一的输出目录，则在该目录下为每个任务创建子目录
                if batch_output_dir:
                    # 使用任务原本的输出目录名作为子目录名
                    sub_dir_name = os.path.basename(output_dir.rstrip('/\\'))
                    if not sub_dir_name:
                        # 如果输出目录名无效，使用URL中的域名
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        sub_dir_name = parsed.netloc.replace(':', '_') or f"task_{len(processed_tasks) + 1}"
                    output_dir = os.path.join(batch_output_dir, sub_dir_name)
                
                if base_url and not url.startswith(('http://', 'https://', 'data:')):
                    from urllib.parse import urljoin
                    url = urljoin(base_url, url)
                if not url.startswith(('http://', 'https://')):
                    url = f"https://{url}"
                processed_tasks.append((url, output_dir))

            if batch_output_dir:
                self._log_message(f"使用统一输出目录，每个任务将保存到独立子目录: {batch_output_dir}", 'info')
            self._log_message(f"准备处理 {len(processed_tasks)} 个任务", 'info')
            all_stats = await process_batch_tasks(
                tasks=processed_tasks,
                timeout=timeout,
                user_agent=user_agent,
                proxy=proxy,
                ext=ext,
                verbose=verbose,
                parallel=parallel,
                auth_file=auth_file
            )
            return all_stats

        try:
            all_stats = asyncio.run(run())
            if all_stats:
                self._show_batch_result(all_stats)
        except Exception as e:
            if not self.cancel_flag:
                self._log_message(f"批量处理失败: {e}", 'error')

    def _show_single_result(self, stats):
        """显示单 URL 模式结果"""
        if not stats:
            return

        total = stats.get('total', 0)
        success = stats.get('success', 0)
        failed = stats.get('failed', 0)

        self._log_message("=" * 60, 'info')
        self._log_message("图片提取完成", 'success')
        self._log_message("=" * 60, 'info')
        self._log_message(f"URL: {stats.get('url', '')}", 'info')
        self._log_message(f"保存到: {stats.get('output_dir', '')}", 'info')

        if stats.get('auth_used'):
            self._log_message(f"认证: 已使用 | 登录: {'成功' if stats.get('login_successful') else '失败'}", 'info')

        self._log_message(f"找到图片: {total}", 'info')
        self._log_message(f"成功提取: {success}", 'success')
        self._log_message(f"提取失败: {failed}", 'error' if failed > 0 else 'info')

        if total > 0:
            rate = success / total * 100
            self._log_message(f"成功率: {rate:.1f}%", 'info')

        self._log_message("=" * 60, 'info')

        # 更新状态栏
        stats_text = f"图片: {success}/{total}  |  成功: {success}  失败: {failed}"
        self._update_status("✅ 处理完成", stats_text)

    def _show_batch_result(self, all_stats):
        """显示批量模式结果"""
        if not all_stats:
            return

        total_tasks = len(all_stats)
        successful_tasks = sum(1 for s in all_stats if s.get('success', 0) > 0 or s.get('has_fallback_urls', False))
        failed_tasks = total_tasks - successful_tasks

        total_images = sum(s.get('total', 0) for s in all_stats)
        total_success = sum(s.get('success', 0) for s in all_stats)
        total_failed = sum(s.get('failed', 0) for s in all_stats)

        auth_used_tasks = sum(1 for s in all_stats if s.get('auth_used', False))
        successful_auth_tasks = sum(1 for s in all_stats if s.get('auth_used', False) and s.get('login_successful', False))

        self._log_message("=" * 60, 'info')
        self._log_message("批量处理完成", 'success')
        self._log_message("=" * 60, 'info')
        self._log_message(f"总任务数: {total_tasks}", 'info')
        self._log_message(f"成功任务: {successful_tasks}", 'success')
        self._log_message(f"失败任务: {failed_tasks}", 'error' if failed_tasks > 0 else 'info')

        if auth_used_tasks > 0:
            self._log_message(f"使用认证的任务: {auth_used_tasks}", 'info')
            self._log_message(f"认证成功: {successful_auth_tasks}", 'info')

        self._log_message(f"总图片数: {total_images}", 'info')
        self._log_message(f"成功提取: {total_success}", 'success')
        self._log_message(f"提取失败: {total_failed}", 'error' if total_failed > 0 else 'info')

        if total_images > 0:
            rate = total_success / total_images * 100
            self._log_message(f"总成功率: {rate:.1f}%", 'info')

        self._log_message("\n任务详情:", 'info')
        for i, s in enumerate(all_stats, 1):
            if 'error' in s:
                self._log_message(f"  {i}. {s['url']} - 错误: {s['error']}", 'error')
            elif s.get('has_fallback_urls', False):
                auth_info = ""
                if s.get('auth_used'):
                    auth_info = f" (认证: {'成功' if s.get('login_successful') else '失败'})"
                self._log_message(f"  {i}. {s['url']} - 找到 {len(s.get('fallback_urls', []))} 个URL(未提取){auth_info}", 'warning')
            else:
                auth_info = ""
                if s.get('auth_used'):
                    auth_info = f" (认证: {'成功' if s.get('login_successful') else '失败'})"
                self._log_message(f"  {i}. {s['url']} - {s.get('success', 0)}/{s.get('total', 0)} 图片{auth_info}", 'info')

        self._log_message("=" * 60, 'info')

        # 更新状态栏
        stats_text = f"任务: {successful_tasks}/{total_tasks}  |  图片: {total_success}/{total_images}"
        self._update_status("✅ 批量处理完成", stats_text)

    def _on_close(self):
        """窗口关闭事件"""
        if self.is_running:
            if messagebox.askokcancel("退出", "正在处理中，确定要退出吗？"):
                self.cancel_flag = True
                self.root.destroy()
        else:
            self.root.destroy()


# ============================================================
# 程序入口
# ============================================================
def main():
    root = Tk()
    app = GetImagesFromUrlGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
