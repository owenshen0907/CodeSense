import os
import json
import argparse
import logging
import time

from model_api_client import call_model_api


def save_scan_json(scan_json_path, data):
    with open(scan_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logging.info(f"保存扫描结果至 {scan_json_path}")


def load_scan_json(scan_json_path):
    if os.path.exists(scan_json_path):
        with open(scan_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info(f"成功加载扫描结果 {scan_json_path}")
        return data
    logging.error(f"扫描结果文件 {scan_json_path} 不存在")
    return None


def extract_initial_summary_from_project_structure(structure, project_path):
    """
    从扫描结果 JSON 中查找项目根目录下的 readme.md（忽略大小写），
    并读取其内容作为初步描述；如果未找到，则返回空字符串。
    依据 project_path 构造绝对路径。
    """
    if not structure or "children" not in structure:
        return ""
    for item in structure["children"]:
        if item.get("type") == "file" and item.get("name", "").lower() == "readme.md":
            file_rel_path = item.get("relative_path")
            abs_file_path = os.path.join(project_path, file_rel_path)
            try:
                with open(abs_file_path, "r", encoding="utf-8") as f:
                    summary = f.read()
                    logging.info(f"提取初步总结成功：{file_rel_path} (字符数：{len(summary)})")
                    return summary
            except Exception as e:
                logging.error(f"读取 {abs_file_path} 失败：{e}")
    return ""


def read_file_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logging.debug(f"读取文件 {file_path} 成功，字符数：{len(content)}")
        return content
    except Exception as e:
        logging.warning(f"读取文件 {file_path} 失败：{e}")
        return ""


def clean_response_text(text):
    """
    预处理模型返回的文本，移除 Markdown 代码块标记
    """
    text = text.strip()
    if text.startswith("```json"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def summarize_files_batch(file_paths, project_path, prompt_template):
    """
    针对多个代码文件生成摘要。
    拼接文件内容时采用以下格式：

      【文件路径：<file_path>】
      【开始】
      <文件内容>
      【结束】
      ===FILE_SEPARATOR===

    将拼接后的内容填入提示词中 {batch_content} 部分调用模型，
    要求模型严格以 JSON 格式输出结果，格式要求为：
      {
        "文件路径1": {"functions": [...], "summary": "..."},
        "文件路径2": {"functions": [...], "summary": "..."},
        ...
      }
    """
    batch_content_list = []
    for fp in file_paths:
        abs_fp = os.path.join(project_path, fp)
        content = read_file_content(abs_fp)
        file_text = f"【文件路径：{fp}】\n【开始】\n{content}\n【结束】"
        batch_content_list.append(file_text)
    batch_content = "\n===FILE_SEPARATOR===\n".join(batch_content_list)
    prompt = prompt_template.format(batch_content=batch_content)
    logging.info(f"【批量摘要】发送给大模型的 prompt（前500字符）：{prompt[:500]}...")
    messages = [{"role": "user", "content": prompt}]
    response = call_model_api(messages, stream=True)
    if response is None:
        logging.error("批量文件摘要生成失败，返回结果为 None")
        return {}
    logging.info("批量文件摘要生成完成")
    logging.info(f"【批量摘要】大模型返回的原始文本（前500字符）：{response[:500]}")
    response_clean = clean_response_text(response)
    try:
        batch_summary = json.loads(response_clean)
    except Exception as e:
        logging.error(f"解析批量摘要 JSON 失败：{e}")
        logging.error("模型返回的文本为：")
        logging.error(response_clean)
        batch_summary = {}
    return batch_summary


def aggregate_final_summary(initial_summary, code_summaries, prompt_template):
    """
    将初步总结与所有文件的代码摘要整合，调用模型生成最终的项目总结报告。
    """
    aggregated = "\n\n".join([f"【{fp}】\n{cs}" for fp, cs in code_summaries.items() if cs])
    prompt = prompt_template.format(initial_summary=initial_summary, code_summaries=aggregated)
    logging.info(f"【最终报告】发送给大模型的 prompt（前500字符）：{prompt[:500]}...")
    messages = [{"role": "user", "content": prompt}]
    response = call_model_api(messages, stream=True)
    if response:
        logging.info("最终项目总结报告生成完成")
    else:
        logging.error("最终项目总结报告生成失败")
    logging.info(f"【最终报告】大模型返回的原始文本（前500字符）：{response[:500] if response else '无'}")
    return response


def update_structure_summary(node, file_rel, summary):
    """
    递归遍历结构树，若遇到文件节点且 relative_path 与 file_rel 匹配，
    则将该节点的 "summaries" 字段更新为 summary。
    """
    if node.get("type") == "file" and node.get("relative_path") == file_rel:
        node["summaries"] = summary
        logging.info(f"回填摘要到结构节点：{file_rel}")
        return True
    if node.get("type") == "dir":
        for child in node.get("children", []):
            if update_structure_summary(child, file_rel, summary):
                return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="CodeSense 项目总结工具：根据扫描结果生成项目总结报告（批量处理文件摘要）"
    )
    parser.add_argument("--project_name", type=str, required=True, help="项目名称")
    parser.add_argument("--scan_json", type=str, required=True, help="扫描结果 JSON 文件路径")
    parser.add_argument("--project_path", type=str, required=True, help="待扫描项目的根目录路径")
    parser.add_argument("--summarizer_config", type=str, default="codesense_summarizer_config.json",
                        help="总结工具配置文件路径")
    parser.add_argument("--output", type=str, default="final_project_summary.md", help="最终总结报告输出文件名称")
    args = parser.parse_args()

    # 加载扫描结果 JSON（应包含预留字段 traversal_order 与 summaries）
    scan_data = load_scan_json(args.scan_json)
    if not scan_data:
        logging.error(f"扫描结果文件 {args.scan_json} 不存在或内容为空")
        return

    # 初步总结：从扫描结果中查找项目根目录下的 readme.md（基于 project_path）
    initial_summary = extract_initial_summary_from_project_structure(scan_data.get("structure", {}), args.project_path)
    if not initial_summary:
        logging.warning("未在扫描结果中找到 readme.md，初步总结为空。")
        initial_summary = ""

    with open(args.summarizer_config, "r", encoding="utf-8") as f:
        summarizer_config = json.load(f)
    batch_summary_prompt = summarizer_config.get("batch_summary_prompt",
                                                 "请针对以下多个代码文件内容，生成每个文件的代码摘要。请严格以 JSON 格式输出结果，格式要求如下：\n{{\n  \"文件路径1\": {{\"functions\": [{{\"name\": \"...\", \"purpose\": \"...\", \"parameters\": \"...\"}}], \"summary\": \"...\"}},\n  \"文件路径2\": {{\"functions\": [{{\"name\": \"...\", \"purpose\": \"...\", \"parameters\": \"...\"}}], \"summary\": \"...\"}},\n  ...\n}}\n\n文件之间使用 '===FILE_SEPARATOR===' 分隔，以下是多个代码文件的内容：\n{batch_content}")
    final_summary_prompt = summarizer_config.get("final_summary_prompt",
                                                 "请将以下初步项目总结与所有代码文件的摘要进行整合，生成最终的项目总结报告。报告需要包含标题与功能介绍、代码摘要、技术标签、关键词和编译/运行环境，并给出与初步总结的对比备注。\n\n初步总结：\n{initial_summary}\n\n代码摘要合集：\n{code_summaries}\n\n请输出整合后的最终总结。")
    max_context = summarizer_config.get("max_context_length", 100000)
    batch_threshold = max_context / 2  # 使用 100000/2 个字符作为批量上限

    # 新增最大调用次数配置
    max_invocations = summarizer_config.get("max_invocations", None)
    invocation_count = 0

    def extract_files(node, flist):
        if node.get("type") == "file":
            flist.append(node.get("relative_path"))
        elif node.get("type") == "dir":
            for child in node.get("children", []):
                extract_files(child, flist)

    file_list = []
    extract_files(scan_data.get("structure", {}), file_list)
    total_files = len(file_list)
    logging.info(f"共计待处理 {total_files} 个文件")

    # 已生成的摘要存放在 scan_data["summaries"]
    summaries = scan_data.get("summaries", {})

    def get_file_char_count(file_rel):
        def recursive_search(node, target):
            if node.get("relative_path") == target:
                return node.get("character_count", 0) or 0
            if node.get("type") == "dir":
                for child in node.get("children", []):
                    res = recursive_search(child, target)
                    if res is not None:
                        return res
            return None

        count = recursive_search(scan_data.get("structure", {}), file_rel)
        if count is None:
            abs_fp = os.path.join(args.project_path, file_rel)
            try:
                with open(abs_fp, "r", encoding="utf-8") as f:
                    count = len(f.read())
            except Exception:
                count = 0
        return count

    pending_files = [fp for fp in file_list if not summaries.get(fp)]
    batch_files = []
    batch_char_count = 0
    i = 0
    while i < len(pending_files):
        if max_invocations is not None and invocation_count >= max_invocations:
            logging.warning(f"达到最大调用次数 {max_invocations}，停止处理剩余文件。")
            break
        fp = pending_files[i]
        char_count = get_file_char_count(fp)
        if char_count >= batch_threshold:
            if batch_files:
                batch_result = summarize_files_batch(batch_files, args.project_path, batch_summary_prompt)
                invocation_count += 1
                for key, value in batch_result.items():
                    summaries[key] = value
                    update_structure_summary(scan_data["structure"], key, value)
                batch_files = []
                batch_char_count = 0
            batch_result = summarize_files_batch([fp], args.project_path, batch_summary_prompt)
            invocation_count += 1
            summary = batch_result.get(fp, "")
            summaries[fp] = summary
            update_structure_summary(scan_data["structure"], fp, summary)
            i += 1
        else:
            if batch_char_count + char_count <= batch_threshold:
                batch_files.append(fp)
                batch_char_count += char_count
                i += 1
            else:
                batch_result = summarize_files_batch(batch_files, args.project_path, batch_summary_prompt)
                invocation_count += 1
                for key, value in batch_result.items():
                    summaries[key] = value
                    update_structure_summary(scan_data["structure"], key, value)
                batch_files = []
                batch_char_count = 0
    if batch_files:
        batch_result = summarize_files_batch(batch_files, args.project_path, batch_summary_prompt)
        invocation_count += 1
        for key, value in batch_result.items():
            summaries[key] = value
            update_structure_summary(scan_data["structure"], key, value)
    scan_data["summaries"] = summaries
    save_scan_json(args.scan_json, scan_data)

    final_summary = aggregate_final_summary(initial_summary, summaries, final_summary_prompt)
    scan_results_dir = os.path.dirname(os.path.abspath(args.scan_json))
    final_output_path = os.path.join(scan_results_dir, args.output)
    with open(final_output_path, "w", encoding="utf-8") as f:
        f.write(final_summary)
    logging.info(f"最终项目总结报告已保存至 {final_output_path}")


def update_structure_summary(node, file_rel, summary):
    """
    递归遍历结构树，若遇到文件节点且 relative_path 与 file_rel 匹配，
    则将该节点的 "summaries" 字段更新为 summary。
    """
    if node.get("type") == "file" and node.get("relative_path") == file_rel:
        node["summaries"] = summary
        logging.info(f"回填摘要到结构节点：{file_rel}")
        return True
    if node.get("type") == "dir":
        for child in node.get("children", []):
            if update_structure_summary(child, file_rel, summary):
                return True
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()