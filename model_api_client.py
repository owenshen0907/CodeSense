import configparser
import time
import requests
import json
import logging

def flush_reasoning_line(buffer, width=40, threshold=5):
    """
    参数:
      buffer: 待处理的字符串
      width: 指定每行最大字符数
      threshold: 至少保留多少个字符之后再允许断行
    返回:
      一个 tuple(line, remaining)，line 为本次分割出的行，remaining 为剩余字符串
    """
    if len(buffer) < width:
        return None, buffer
    punctuation = "，。；、！？“”‘’"  # 可扩展其它中文标点
    candidate_idx = -1
    for i in range(width - 1, threshold - 1, -1):
        if buffer[i] in punctuation:
            candidate_idx = i
            break
    if candidate_idx != -1:
        line = buffer[:candidate_idx + 1]
        remaining = buffer[candidate_idx + 1:]
    else:
        line = buffer[:width]
        remaining = buffer[width:]
    return line, remaining

def read_model_api_config(config_file="config.ini"):
    """
    读取配置文件，返回 API Key、API URL 以及 displayLLM 参数。
    displayLLM 决定是否在终端输出大模型请求和响应的详细内容。
    """
    config = configparser.ConfigParser()
    config.read(config_file)
    api_key = config.get('step_api_prod', 'key')
    api_url = config.get('step_api_prod', 'url')
    try:
        display_llm = config.getboolean("logging", "displayLLM")
    except Exception:
        display_llm = False
    return api_key, api_url, display_llm

STEP_API_KEY, BASE_URL, DISPLAY_LLM = read_model_api_config()

# 选择使用的模型
COMPLETION_MODEL = "step-r1-v-mini"

def call_model_api(messages, model=COMPLETION_MODEL, stream=False, timeout=60, big_model_log_path="big_model_calls.log"):
    """
    调用模型 API，发送消息列表 messages。

    参数:
      messages: 消息列表（格式参照 ChatGPT 格式）
      model: 模型名称
      stream: 是否采用流式返回
      timeout: 请求超时时间
      big_model_log_path: 大模型调用日志文件存放路径

    返回:
      当 stream=False 时，直接返回生成的文本；
      当 stream=True 时，实时记录返回过程（含思考过程断行显示），并返回最终生成的文本。

    大模型调用的详细输入、输出和 Trace ID 将写入 big_model_log_path 文件，
    同时 Trace ID 总是在终端显示（便于快速定位问题）。
    """
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {STEP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream
    }
    try:
        response = requests.post(url, headers=headers, json=payload, stream=stream, timeout=timeout)
        traceid = response.headers.get('X-Trace-ID')
        # 写入 Trace ID 到 big_model_log_path 文件，并 flush
        with open(big_model_log_path, "a", encoding="utf-8") as f:
            f.write(f"Trace ID: {traceid}\n")
            f.flush()
        # 始终在终端显示 Trace ID
        print(f"Trace ID: {traceid}")
        if response.status_code != 200:
            print(f"请求失败，状态码：{response.status_code}")
            try:
                error_info = response.json()
                print("错误详情:", json.dumps(error_info, ensure_ascii=False, indent=2))
            except Exception as e:
                print("解析错误详情失败:", e)
            return None
    except requests.RequestException as e:
        print(f"请求 API 时发生异常：{e}")
        return None

    if not stream:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            with open(big_model_log_path, "a", encoding="utf-8") as f:
                f.write("大模型返回内容:\n" + content + "\n")
                f.flush()
            return content
        except Exception as e:
            print(f"解析响应失败: {e}")
            return None
    else:
        final_content = ""
        print("【模型推理中…】")
        with open(big_model_log_path, "a", encoding="utf-8") as f:
            f.write("【模型推理中…】\n")
            f.flush()
        reasoning_buffer = ""
        reasoning_header_printed = False
        for chunk in response.iter_lines():
            if chunk:
                decoded = chunk.decode('utf-8')
                if decoded == "data: [DONE]":
                    break
                if decoded.startswith("data: "):
                    json_str = decoded[6:].strip()
                    try:
                        data = json.loads(json_str)
                        delta = data["choices"][0]["delta"]
                        if "reasoning" in delta:
                            reasoning_chunk = delta.get("reasoning", "")
                            if reasoning_chunk:
                                if not reasoning_header_printed:
                                    if DISPLAY_LLM:
                                        print("\n\n[思考过程]:")
                                    with open(big_model_log_path, "a", encoding="utf-8") as f:
                                        f.write("\n\n[思考过程]:\n")
                                        f.flush()
                                    reasoning_header_printed = True
                                reasoning_buffer += reasoning_chunk
                                while len(reasoning_buffer) >= 40:
                                    line, reasoning_buffer = flush_reasoning_line(reasoning_buffer, width=40)
                                    if line:
                                        if DISPLAY_LLM:
                                            print(line)
                                        with open(big_model_log_path, "a", encoding="utf-8") as f:
                                            f.write(line + "\n")
                                            f.flush()
                        content = delta.get("content", "")
                        if content:
                            if DISPLAY_LLM:
                                print(content, end='', flush=True)
                            final_content += content
                            with open(big_model_log_path, "a", encoding="utf-8") as f:
                                f.write(content)
                                f.flush()
                    except Exception as e:
                        print(f"\n解析流响应错误: {e}")
        if reasoning_buffer:
            if DISPLAY_LLM:
                print(reasoning_buffer)
            with open(big_model_log_path, "a", encoding="utf-8") as f:
                f.write(reasoning_buffer + "\n")
                f.flush()
        if DISPLAY_LLM:
            print("\n【模型推理完成】")
        with open(big_model_log_path, "a", encoding="utf-8") as f:
            f.write("\n【模型推理完成】\n")
            f.flush()
        return final_content