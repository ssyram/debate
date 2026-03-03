#!/usr/bin/env python3
"""Launcher — 默认启动 Web 版本

用法:
    python new_debate.py              # 启动 Web 版本（默认）
    python new_debate.py --cli        # 启动命令行版本
    python new_debate.py --web        # 启动 Web 版本
    python new_debate.py --port 8080  # 指定端口
"""
import sys

def main():
    # 默认启动 Web 版本
    if len(sys.argv) == 1 or "--web" in sys.argv:
        # 提取端口参数
        port = 5000
        for i, arg in enumerate(sys.argv):
            if arg in ["--port", "-p"] and i + 1 < len(sys.argv):
                try:
                    port = int(sys.argv[i + 1])
                except ValueError:
                    print(f"无效的端口号: {sys.argv[i + 1]}")
                    sys.exit(1)
        
        # 导入并启动 Web 版本
        from debate_tool.web.__main__ import main as web_main
        import argparse
        
        # 模拟命令行参数
        sys.argv = ["debate_tool.web", "--port", str(port)]
        web_main()
    
    elif "--cli" in sys.argv:
        # 启动命令行版本
        from debate_tool.__main__ import main as cli_main
        # 移除 --cli 参数
        sys.argv = [arg for arg in sys.argv if arg != "--cli"]
        cli_main()
    else:
        # 如果没有明确的标志，默认启动 Web 版本
        from debate_tool.web.__main__ import main as web_main
        sys.argv = ["debate_tool.web"]
        web_main()

if __name__ == "__main__":
    main()
