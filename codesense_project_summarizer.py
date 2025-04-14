import os
import json
import argparse
import logging
import sys
import time
import configparser
import datetime
from model_api_client import call_model_api

# 全局变量，默认大模型调用日志文件路径，后续在 main_wrapper 中会更新
BIG_MODEL_LOG = "big_model_calls.log"


def setup_logging(log_dir):
    """
    配置日志：
      - 所有日志 DEBUG 及以上写入 log_dir/debug.log 文件
      - 终端上显示全部日志
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, "debug.log")
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fh_formatter)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    ch.setFormatter(ch_formatter)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    logging.debug(f"日志系统初始化完成，日志文件：{log_file}")


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
    if not structure or "children" not in structure:
        return ""
    for item in structure["children"]:
        if item.get("type") == "file" and item.get("name", "").lower() == "readme.md":
            file_rel_path = item.get("relative_path")
            abs_file_path = os.path.join(project_path, file_rel_path)
            try:
                with open(abs_file_path, "r", encoding="utf-8") as f:
                    summary = f.read()
                    logging.info(f"提取 readme.md 成功：{file_rel_path} (字符数：{len(summary)})")
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
    针对一批代码文件生成摘要（不包括 .md 文件）。
    拼接时采用格式：
      【文件路径：<file_path>】
      【开始】
      <文件内容>
      【结束】
      ===FILE_SEPARATOR===
    将所有文本填入 prompt_template 的 {batch_content} 部分，调用大模型生成摘要。
    """
    batch_content_list = []
    for fp in file_paths:
        abs_fp = os.path.join(project_path, fp)
        content = read_file_content(abs_fp)
        file_text = f"【文件路径：{fp}】\n【开始】\n{content}\n【结束】"
        batch_content_list.append(file_text)
    batch_content = "\n===FILE_SEPARATOR===\n".join(batch_content_list)
    prompt = prompt_template.format(batch_content=batch_content)
    messages = [{"role": "user", "content": prompt}]
    response = call_model_api(messages, stream=True, big_model_log_path=BIG_MODEL_LOG)
    if response is None:
        logging.error("批量文件摘要生成失败，返回结果为 None")
        return {}
    logging.info("批量文件摘要生成完成")
    response_clean = clean_response_text(response)
    try:
        batch_summary = json.loads(response_clean)
    except Exception as e:
        logging.error(f"解析批量摘要 JSON 失败：{e}")
        logging.error("大模型返回的文本为：")
        logging.error(response_clean)
        batch_summary = {}
    return batch_summary


def aggregate_final_summary(initial_summary, code_summaries, prompt_template):
    aggregated = "\n\n".join([f"【{fp}】\n{cs}" for fp, cs in code_summaries.items() if cs])
    prompt = prompt_template.format(initial_summary=initial_summary, code_summaries=aggregated)
    messages = [{"role": "user", "content": prompt}]
    response = call_model_api(messages, stream=True, big_model_log_path=BIG_MODEL_LOG)
    if response:
        logging.info("最终项目总结报告生成完成")
    else:
        logging.error("最终项目总结报告生成失败")
    return response


def update_structure_summary(node, file_rel, summary):
    if node.get("type") == "file" and node.get("relative_path") == file_rel:
        node["summaries"] = summary
        node["need_traverse"] = False
        logging.info(f"回填摘要到结构节点：{file_rel}，并将 need_traverse 设置为 False")
        return True
    if node.get("type") == "dir":
        for child in node.get("children", []):
            if update_structure_summary(child, file_rel, summary):
                return True
    return False


def estimate_invocations(file_list, get_file_char_count, batch_threshold):
    pending = file_list[:]  # 复制列表
    count = 0
    i = 0
    while i < len(pending):
        char_count = get_file_char_count(pending[i])
        if char_count >= batch_threshold:
            count += 1
            i += 1
        else:
            total = char_count
            i += 1
            while i < len(pending) and total + get_file_char_count(pending[i]) <= batch_threshold:
                total += get_file_char_count(pending[i])
                i += 1
            count += 1
    return count


def extract_files(node, flist):
    if node.get("type") == "file":
        if (not node.get("name", "").lower().endswith(".md")) and node.get("need_traverse", True):
            flist.append(node.get("relative_path"))
    elif node.get("type") == "dir":
        for child in node.get("children", []):
            extract_files(child, flist)
    return flist


def collect_pending_files(node, pending_list=None):
    if pending_list is None:
        pending_list = []
    if node.get("type") == "file":
        if (not node.get("name", "").lower().endswith(".md")) and node.get("need_traverse", True) and not node.get(
                "summaries"):
            pending_list.append(node.get("relative_path"))
    elif node.get("type") == "dir":
        for child in node.get("children", []):
            collect_pending_files(child, pending_list)
    return pending_list


def main():
    parser = argparse.ArgumentParser(
        description="CodeSense 项目总结工具：生成项目总结报告（批量处理文件摘要，支持多种场景）"
    )
    parser.add_argument("--project_name", type=str, required=True, help="项目名称")
    parser.add_argument("--scan_json", type=str, required=True, help="扫描结果 JSON 文件路径")
    parser.add_argument("--project_path", type=str, required=True, help="待扫描项目根目录路径")
    parser.add_argument("--summarizer_config", type=str, default="codesense_summarizer_config.json",
                        help="总结工具配置文件路径")
    # 此处 output 参数仅作基文件名前缀，但最终生成的 md 文件名由场景配置决定并附加日期时间
    parser.add_argument("--output", type=str, default="final_project_summary.md",
                        help="最终总结报告输出文件名称（基文件名，含扩展名）")
    parser.add_argument("--scenario", type=str, choices=["direct", "correct", "usage", "custom"], default="direct",
                        help="选择总结场景")
    args = parser.parse_args()

    # 加载扫描结果 JSON
    scan_data = load_scan_json(args.scan_json)
    if not scan_data:
        logging.error(f"扫描结果文件 {args.scan_json} 不存在或内容为空")
        return

    # 提取原始 readme 内容作为初步总结
    initial_summary = extract_initial_summary_from_project_structure(scan_data.get("structure", {}), args.project_path)
    if not initial_summary:
        logging.warning("未在扫描结果中找到 readme.md，初步总结为空。")
        initial_summary = ""

    with open(args.summarizer_config, "r", encoding="utf-8") as f:
        summarizer_config = json.load(f)
    logging.info(f"加载总结工具配置文件：{args.summarizer_config}")

    # 从配置中选择指定场景的配置项
    scenarios = summarizer_config.get("scenarios", {})
    if args.scenario not in scenarios:
        logging.error(f"配置文件中不包含场景 {args.scenario}")
        sys.exit(1)
    scenario_conf = scenarios[args.scenario]

    # 根据场景决定是否使用原始 readme
    use_initial_readme = scenario_conf.get("use_initial_readme", True)
    if not use_initial_readme:
        initial_summary = ""

    batch_summary_prompt = scenario_conf.get("batch_summary_prompt", "")
    final_summary_prompt = scenario_conf.get("final_summary_prompt", "")
    if final_summary_prompt == "":
        logging.warning("当前场景的 final_summary_prompt 为空，请在配置文件中配置或选择其他场景。")

    max_context = summarizer_config.get("max_context_length", 100000)
    batch_threshold = max_context / 2

    max_invocations = summarizer_config.get("max_invocations", None)
    invocation_count = 0

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

    pending_files = collect_pending_files(scan_data.get("structure", {}))
    total_files = len(pending_files)
    logging.info(f"待处理文件数量（不包含 .md 文件且 need_traverse 为 True）：{total_files}")

    estimated_invocations = estimate_invocations(pending_files, lambda fp: get_file_char_count(fp), batch_threshold)
    total_steps = 1 + estimated_invocations + 1
    logging.info(f"预估大模型调用总次数：{estimated_invocations}，总步骤数：{total_steps}")
    logging.info(f"进度：初步总结步骤完成，占总进度 {(1 / total_steps) * 100:.1f}%")

    summaries = scan_data.get("summaries", {})

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
                progress = ((1 + invocation_count) / total_steps) * 100
                logging.info(f"进度：已完成 {progress:.1f}%")
                save_scan_json(args.scan_json, scan_data)
            batch_result = summarize_files_batch([fp], args.project_path, batch_summary_prompt)
            invocation_count += 1
            summary = batch_result.get(fp, "")
            summaries[fp] = summary
            update_structure_summary(scan_data["structure"], fp, summary)
            progress = ((1 + invocation_count) / total_steps) * 100
            logging.info(f"进度：已完成 {progress:.1f}%")
            save_scan_json(args.scan_json, scan_data)
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
                progress = ((1 + invocation_count) / total_steps) * 100
                logging.info(f"进度：已完成 {progress:.1f}%")
                save_scan_json(args.scan_json, scan_data)
    if batch_files:
        batch_result = summarize_files_batch(batch_files, args.project_path, batch_summary_prompt)
        invocation_count += 1
        for key, value in batch_result.items():
            summaries[key] = value
            update_structure_summary(scan_data["structure"], key, value)
        progress = ((1 + invocation_count) / total_steps) * 100
        logging.info(f"进度：已完成 {progress:.1f}%")
        save_scan_json(args.scan_json, scan_data)
    scan_data["summaries"] = summaries
    save_scan_json(args.scan_json, scan_data)

    final_summary = aggregate_final_summary(initial_summary, summaries, final_summary_prompt)
    invocation_count += 1
    progress = ((1 + invocation_count) / total_steps) * 100
    logging.info(f"进度：已完成 {progress:.1f}%")

    # 根据当前场景配置中的 md_path 生成最终输出文件名
    base_md = scenario_conf.get("md_path", args.output)
    base_name = os.path.splitext(base_md)[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    final_file_name = f"{base_name}_{timestamp}.md"
    scan_results_dir = os.path.dirname(os.path.abspath(args.scan_json))
    final_output_path = os.path.join(scan_results_dir, final_file_name)
    with open(final_output_path, "w", encoding="utf-8") as f:
        f.write(final_summary)
    logging.info(f"最终项目总结报告已保存至 {final_output_path}")


# 重新定义 update_structure_summary（保持一致）
def update_structure_summary(node, file_rel, summary):
    if node.get("type") == "file" and node.get("relative_path") == file_rel:
        node["summaries"] = summary
        node["need_traverse"] = False
        logging.info(f"回填摘要到结构节点：{file_rel}，并将 need_traverse 设置为 False")
        return True
    if node.get("type") == "dir":
        for child in node.get("children", []):
            if update_structure_summary(child, file_rel, summary):
                return True
    return False


def estimate_invocations(file_list, get_file_char_count, batch_threshold):
    pending = file_list[:]  # 复制列表
    count = 0
    i = 0
    while i < len(pending):
        char_count = get_file_char_count(pending[i])
        if char_count >= batch_threshold:
            count += 1
            i += 1
        else:
            total = char_count
            i += 1
            while i < len(pending) and total + get_file_char_count(pending[i]) <= batch_threshold:
                total += get_file_char_count(pending[i])
                i += 1
            count += 1
    return count


def main_wrapper():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project_name", type=str, default="CodeSense")
    parser.add_argument("--scan_json", type=str, default="scan_results/CodeSense/project_structure.json")
    parser.add_argument("--project_path", type=str, default=os.path.dirname(os.path.abspath(__file__)))
    args, unknown = parser.parse_known_args()
    code_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(code_root, "scan_results", args.project_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    setup_logging(output_dir)
    global BIG_MODEL_LOG
    BIG_MODEL_LOG = os.path.join(output_dir, "big_model_calls.log")
    main()


if __name__ == "__main__":
    main_wrapper()