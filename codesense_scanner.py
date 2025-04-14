import os
import json
import argparse
import datetime
import logging

# 默认全局配置（加载配置文件失败时使用）
DEFAULT_CONFIG = {
    "scan_hidden": False,
    "languages": {
        "python": [".py"],
        "javascript": [".js", ".jsx"],
        "typescript": [".ts", ".tsx"],
        "go": [".go"],
        "java": [".java"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".hpp", ".cc", ".cxx"],
        "ruby": [".rb"],
        "php": [".php"],
        "swift": [".swift"],
        "kotlin": [".kt"],
        "scala": [".scala"],
        "r": [".r"],
        "csharp": [".cs"],
        "objective-c": [".m", ".mm"]
    },
    "file_categories": {
        "config": [
            "package.json", "requirements.txt", "Pipfile", "yarn.lock", "Makefile",
            "webpack.config.js", "next.config.js", ".babelrc", ".eslintrc", ".prettierrc"
        ],
        "dependency": ["pom.xml", "build.gradle", "Cargo.toml", "composer.json"],
        "runtime": ["next.config.js", ".env"]
    },
    "exclude_dirs": ["node_modules", "dist", "build", ".git", "__pycache__"],
    "binary_extensions": [
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".mp4", ".avi", ".exe", ".dll", ".zip", ".rar"
    ]
}

def is_binary_file(file_path, binary_extensions):
    """根据文件扩展名判断是否为二进制文件"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in binary_extensions

def detect_language(file_name, languages_config):
    """根据文件扩展名判断文件所属开发语言"""
    ext = os.path.splitext(file_name)[1].lower()
    for lang, exts in languages_config.items():
        if ext in exts:
            return lang
    return "unknown"

def detect_category(file_name, file_categories):
    """
    根据文件名判断文件所属类别：
    如果匹配到配置、依赖或运行时文件，则返回对应类别；否则默认为 "code"
    """
    base = os.path.basename(file_name)
    for category, names in file_categories.items():
        if base in names:
            return category
    return "code"

def count_file_characters(file_path):
    """
    尝试以 UTF-8 编码读取文件，并返回字符数；
    若读取失败则返回 None。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return len(content)
    except Exception:
        return None

def scan_directory(path, config, rel_path="", is_root=False):
    """
    递归扫描目录，返回目录结构描述字典：
      - 目录节点包含： type, name, relative_path, children
      - 文件节点包含： type, name, relative_path, language, category, is_text, character_count,
                         need_traverse, summaries
    参数 is_root 用于第一次调用时，避免将项目根目录名称加入相对路径中。
    """
    basename = os.path.basename(path)
    # 根目录时不将名称加入 relative_path
    current_rel_path = "" if is_root else (os.path.join(rel_path, basename) if rel_path else basename)

    # 判断是否扫描隐藏目录或文件（以 "." 开头）
    if not config.get("scan_hidden", False) and basename.startswith('.'):
        return None

    # 排除配置中指定的不扫描目录
    if basename in config.get("exclude_dirs", []):
        return None

    if os.path.isdir(path):
        dir_dict = {
            "type": "dir",
            "name": basename,
            "relative_path": current_rel_path,
            "children": []
        }
        try:
            for entry in os.listdir(path):
                full_path = os.path.join(path, entry)
                child = scan_directory(full_path, config, current_rel_path, is_root=False)
                if child is not None:
                    dir_dict["children"].append(child)
        except PermissionError:
            dir_dict["children"].append({
                "type": "dir",
                "name": "Permission Denied",
                "relative_path": current_rel_path,
                "children": []
            })
        return dir_dict
    else:
        file_info = {
            "type": "file",
            "name": basename,
            "relative_path": current_rel_path,
        }
        if is_binary_file(path, config.get("binary_extensions", [])):
            file_info["is_text"] = False
            file_info["character_count"] = None
        else:
            file_info["is_text"] = True
            file_info["character_count"] = count_file_characters(path)
        file_info["language"] = detect_language(basename, config.get("languages", {}))
        file_info["category"] = detect_category(basename, config.get("file_categories", {}))
        # 为每个文件增加预留字段，表示是否需要遍历文件内容，默认值为 True（是）
        file_info["need_traverse"] = True
        file_info["summaries"] = {}
        return file_info

def generate_tree_markdown(node, indent=0):
    """
    递归生成 Markdown 格式的树状目录结构字符串
    """
    lines = []
    prefix = " " * (indent * 4)  # 每级缩进 4 个空格
    if node["type"] == "dir":
        lines.append(f"{prefix}- **{node['name']}**")
        for child in node.get("children", []):
            lines.append(generate_tree_markdown(child, indent + 1))
    elif node["type"] == "file":
        lines.append(f"{prefix}- {node['name']}")
    return "\n".join(lines)

def collect_file_names(node, file_list=None):
    """
    递归收集所有文件的相对路径到一个列表中
    """
    if file_list is None:
        file_list = []
    if node["type"] == "file":
        file_list.append(node["relative_path"])
    elif node["type"] == "dir":
        for child in node.get("children", []):
            collect_file_names(child, file_list)
    return file_list

def setup_logging():
    """
    在 CodeSense 根目录下创建 logs 文件夹，并配置日志记录（按天归档）
    """
    code_root = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(code_root, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    today_str = datetime.datetime.today().strftime("%Y-%m-%d")
    log_file = os.path.join(logs_dir, f"{today_str}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    logging.info(f"日志记录初始化：日志文件 -> {log_file}")

def merge_summaries(old_node, new_node):
    """
    递归合并旧结构和新结构：
      - 如果新节点为文件且旧节点已有 summaries，则保留旧 summaries，
        同时如果旧节点的 need_traverse 为 False，则更新新节点状态为 False
      - 对于目录，递归合并子节点
    """
    if new_node.get("type") == "file":
        if old_node:
            if old_node.get("summaries"):
                new_node["summaries"] = old_node["summaries"]
            if old_node.get("need_traverse") is False:
                new_node["need_traverse"] = False
    elif new_node.get("type") == "dir":
        old_children = {}
        if old_node and "children" in old_node:
            for child in old_node["children"]:
                old_children[child.get("relative_path")] = child
        for child in new_node.get("children", []):
            rel = child.get("relative_path")
            if rel in old_children:
                merge_summaries(old_children[rel], child)
    return new_node

def save_scan_json_with_merge(scan_json_path, new_data):
    """
    如果已有扫描结果文件存在，则先加载旧数据，并将旧数据（例如 summaries 和 need_traverse 状态）合并到 new_data，
    然后写入 scan_json_path。
    """
    if os.path.exists(scan_json_path):
        try:
            with open(scan_json_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if "structure" in new_data and "structure" in old_data:
                new_data["structure"] = merge_summaries(old_data["structure"], new_data["structure"])
            if "summaries" in old_data:
                new_data["summaries"].update(old_data["summaries"])
            logging.info("成功合并已有的扫描结果")
        except Exception as e:
            logging.error(f"合并已有扫描结果失败：{e}")
    with open(scan_json_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=4)
    logging.info(f"保存扫描结果至 {scan_json_path}")

def main():
    parser = argparse.ArgumentParser(
        description="CodeSense 代码扫描工具：生成项目目录结构及文件属性"
    )
    parser.add_argument("--project_name", type=str, default="CodeSense", help="项目名称 (默认: CodeSense)")
    parser.add_argument("--path", type=str, required=True, help="待扫描的项目根目录路径")
    parser.add_argument("--output", type=str, default="project_structure.json", help="输出 JSON 文件名称")
    parser.add_argument("--tree_output", type=str, default="project_tree.md", help="输出树状目录的 Markdown 文件名称")
    parser.add_argument("--file_list_output", type=str, default="project_files.txt", help="输出所有文件相对路径的文本文件名称")
    parser.add_argument("--config", type=str, default=None, help="全局配置文件路径 (JSON格式)，默认加载 codesense_config.json")
    args = parser.parse_args()

    setup_logging()

    # 加载全局配置
    if args.config:
        config_path = args.config
    else:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codesense_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as cf:
            config = json.load(cf)
        logging.info(f"加载全局配置文件：{config_path}")
    except Exception as e:
        logging.error(f"加载全局配置文件失败，将使用默认配置。错误信息：{e}")
        config = DEFAULT_CONFIG

    # 检查项目根目录下是否存在项目级配置文件 codesense_project_config.json
    project_config_path = os.path.join(args.path, "codesense_project_config.json")
    if os.path.exists(project_config_path):
        try:
            with open(project_config_path, "r", encoding="utf-8") as pcf:
                project_config = json.load(pcf)
                config.update(project_config)
            logging.info("已加载项目级配置文件 codesense_project_config.json")
        except Exception as e:
            logging.error(f"加载项目级配置文件失败，继续使用全局配置。错误信息：{e}")

    if not os.path.exists(args.path):
        logging.error(f"错误：提供的待扫描路径 {args.path} 不存在。")
        return

    # 确定输出目录
    code_root = os.path.dirname(os.path.abspath(__file__))
    base_output = os.path.join(code_root, "scan_results")
    if not os.path.exists(base_output):
        os.makedirs(base_output)
    output_dir = os.path.join(base_output, args.project_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 扫描指定项目目录（第一次调用时 is_root=True，不将项目根目录名称加入相对路径）
    directory_structure = scan_directory(args.path, config, rel_path="", is_root=True)

    # 构造最终项目结构 JSON，其中每个文件节点包含预留字段 need_traverse 和 summaries
    project_structure = {
        "project_name": args.project_name,
        "structure": directory_structure,
        "need_traverse": True,
        "summaries": {}
    }

    json_output_path = os.path.join(output_dir, args.output)
    # 使用合并策略保存扫描结果，避免覆盖之前的记录
    save_scan_json_with_merge(json_output_path, project_structure)
    print(f"项目结构及文件信息已保存至 {json_output_path}")

    file_list = collect_file_names(directory_structure)
    file_list_output_path = os.path.join(output_dir, args.file_list_output)
    with open(file_list_output_path, "w", encoding="utf-8") as f:
        for file_name in file_list:
            f.write(file_name + "\n")
    logging.info(f"文件列表已保存至 {file_list_output_path}")

if __name__ == "__main__":
    main()