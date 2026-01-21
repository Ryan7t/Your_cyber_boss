import os
import json
import time
import glob
import traceback
from typing import List, Dict
from colorama import Fore, Style, init
from pyfiglet import Figlet
from openai import OpenAI
from docx import Document
from dotenv import load_dotenv

# 加载 .env 文件
# 显式指定 .env 路径，防止路径问题
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
print(f"{Fore.YELLOW}Debug: Loading .env from: {env_path}{Style.RESET_ALL}")
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True) # override=True 确保覆盖系统环境变量
else:
    print(f"{Fore.RED}Debug: .env file NOT FOUND at {env_path}{Style.RESET_ALL}")

# 初始化控制台美化工具
init()

class SimpleAgent:
    def __init__(self, name):
        self.name = name
        self.memory_file = "conversation_history.json"
        
        # 配置加载
        self.system_prompt_file = "system_prompt.txt"
        self.system_prompt = self._load_system_prompt()
        self.context_intro_file = "context_intro.txt"
        self.context_intro = self._load_context_intro()
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2")
        
        self.memory = self._load_memory()
        self.context = self._load_context()
        
        # 初始化 OpenAI 客户端
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        
        if not api_key:
            print(f"{Fore.RED}警告：未配置有效的 OPENAI_API_KEY。请检查 .env。{Style.RESET_ALL}")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key, base_url=base_url)

        # 欢迎语
        f = Figlet(font='slant')
        print(Fore.CYAN + f.renderText(self.name) + Style.RESET_ALL)
        print(f"我是 {Fore.GREEN}{self.name}{Style.RESET_ALL}，一个带文档阅读能力的AI助手！")
        print(f"当前模型: {Fore.MAGENTA}{self.model_name}{Style.RESET_ALL}")
        if self.context_intro:
             print(f"{Fore.CYAN}已加载上下文引导语。{Style.RESET_ALL}")
        if self.context:
            print(f"{Fore.YELLOW}已加载文档上下文。{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}未加载到任何文档上下文。{Style.RESET_ALL}")

    def _load_system_prompt(self) -> str:
        """从文件加载系统提示词"""
        default_prompt = "你是一个智能助手，请根据提供的上下文回答用户的问题。"
        if os.path.exists(self.system_prompt_file):
            try:
                with open(self.system_prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        print(f"已从 {self.system_prompt_file} 加载系统提示词。")
                        return content
            except Exception as e:
                print(f"{Fore.RED}读取系统提示词文件失败: {e}{Style.RESET_ALL}")
        return default_prompt

    def _load_context_intro(self) -> str:
        """从文件加载上下文引导语"""
        if os.path.exists(self.context_intro_file):
            try:
                with open(self.context_intro_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        print(f"已从 {self.context_intro_file} 加载上下文引导。")
                        return content
            except Exception as e:
                print(f"{Fore.RED}读取上下文引导文件失败: {e}{Style.RESET_ALL}")
        return ""

    def _load_memory(self) -> List[Dict]:
        """加载历史对话记录"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{Fore.RED}加载记忆文件失败: {e}{Style.RESET_ALL}")
        return []

    def _save_memory(self):
        """保存对话记录到文件"""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"{Fore.RED}保存记忆文件失败: {e}{Style.RESET_ALL}")

    def _load_context(self) -> str:
        """解析文案目录下的所有 docx 文件"""
        context_text = ""
        doc_dir = os.path.join(os.getcwd(), "文案")
        
        if not os.path.exists(doc_dir):
            print(f"{Fore.RED}警告: 未找到 '文案' 目录。{Style.RESET_ALL}")
            return ""

        docx_files = glob.glob(os.path.join(doc_dir, "*.docx"))
        
        if not docx_files:
             print(f"{Fore.YELLOW}提示: '文案' 目录下没有 .docx 文件。{Style.RESET_ALL}")
             return ""

        for file_path in docx_files:
            try:
                doc = Document(file_path)
                file_content = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        file_content.append(para.text.strip())
                
                if file_content:
                    filename = os.path.basename(file_path)
                    context_text += f"\n\n--- 文件名: {filename} ---\n"
                    context_text += "\n".join(file_content)
            except Exception as e:
                print(f"{Fore.YELLOW}无法读取文件 {file_path}: {e}{Style.RESET_ALL}")
        
        return context_text

    def think(self, user_input: str) -> List[Dict]:
        """构建发送给 LLM 的消息列表"""
        # 构建完整的 system message
        # 顺序：系统提示词 -> 上下文引导 -> 文档内容
        system_content = f"{self.system_prompt}\n\n"
        
        if self.context_intro:
            system_content += f"【背景设定/引导】\n{self.context_intro}\n\n"
            
        system_content += f"【参考文档内容】\n{self.context}"
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        # 添加历史对话上下文
        for record in self.memory:
            messages.append({"role": "user", "content": record["user_input"]})
            messages.append({"role": "assistant", "content": record["response"]})
            
        messages.append({"role": "user", "content": user_input})
        return messages

    def act(self, messages: List[Dict]):
        """调用 LLM 生成回复 (流式)"""
        if not self.client:
            yield "错误：未配置有效的 OpenAI API Key，无法进行对话。"
            return
            
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name, 
                messages=messages,
                temperature=0.7,
                stream=True  # 开启流式
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception:
            # 打印完整的错误堆栈信息
            error_trace = traceback.format_exc()
            print(f"\n{Fore.RED}======== LLM 调用错误详情 ========{Style.RESET_ALL}")
            print(f"{Fore.RED}{error_trace}{Style.RESET_ALL}")
            print(f"{Fore.RED}=================================={Style.RESET_ALL}")
            yield "调用 LLM 失败，请查看上方红色错误日志。"

    def run(self):
        """智能体主循环"""
        while True:
            user_input = input(f"\n{Fore.BLUE}[{self.name}] 请输入你的问题（输入'exit'退出）：{Style.RESET_ALL}")
            
            if user_input.lower() == "exit":
                print(Fore.RED + "再见！期待下次相遇～" + Style.RESET_ALL)
                break
            
            # 这里的 think 返回的是消息列表
            messages = self.think(user_input)
            
            print(f"\n{Fore.GREEN}[{self.name}回复]{Style.RESET_ALL}", end=" ")
            
            full_response = ""
            try:
                # 迭代流式生成器
                for chunk in self.act(messages):
                    print(chunk, end="", flush=True)
                    full_response += chunk
            except Exception as e:
                print(f"\n{Fore.RED}流式接收出错: {e}{Style.RESET_ALL}")
            
            print() # 换行
            
            # 存储对话到记忆（只存本次交互，历史会在下一次 think 中自动加载）
            self.memory.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "user_input": user_input,
                "response": full_response
            })
            self._save_memory()

if __name__ == "__main__":
    agent = SimpleAgent("DocAgent")
    agent.run()
