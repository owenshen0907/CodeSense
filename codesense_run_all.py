import os
import sys
import subprocess
import argparse

def main():
    # 默认的项目路径和项目名称：当前脚本所在目录
    default_project_path = os.path.dirname(os.path.abspath(__file__))
    default_project_name = os.path.basename(default_project_path)

    parser = argparse.ArgumentParser(description="CodeSense 自动执行扫描与项目总结")
    parser.add_argument("--project_name", type=str, default=default_project_name, help="项目名称（默认为当前项目目录名称）")
    parser.add_argument("--project_path", type=str, default=default_project_path, help="待扫描项目根目录路径（默认为当前项目目录）")
    parser.add_argument("--config", type=str, default="codesense_config.json", help="全局扫描配置文件路径")
    parser.add_argument("--output", type=str, default="project_structure.json", help="扫描结果 JSON 文件名称")
    parser.add_argument("--tree_output", type=str, default="project_tree.md", help="树状目录输出文件名称")
    parser.add_argument("--file_list_output", type=str, default="project_files.txt", help="文件列表输出文件名称")
    parser.add_argument("--summarizer_config", type=str, default="codesense_summarizer_config.json", help="项目总结配置文件路径")
    parser.add_argument("--final_summary", type=str, default="final_project_summary.md", help="最终项目总结报告输出文件名称")
    # 增加 --scenario 参数，用于选择总结场景（direct, correct, usage, custom）
    parser.add_argument("--scenario", type=str, choices=["direct", "correct", "usage", "custom"], default="direct", help="选择总结场景")
    args = parser.parse_args()

    # 调用扫描程序（codesense_scanner.py）
    scan_cmd = [
        sys.executable, "codesense_scanner.py",
        "--project_name", args.project_name,
        "--path", args.project_path,
        "--output", args.output,
        "--tree_output", args.tree_output,
        "--file_list_output", args.file_list_output,
        "--config", args.config
    ]
    print("正在执行项目扫描……")
    ret = subprocess.run(scan_cmd)
    if ret.returncode != 0:
        print("项目扫描失败，请检查日志。")
        sys.exit(ret.returncode)
    else:
        print("项目扫描完成。")

    # 构造扫描结果 JSON 文件路径（假设保存在 scan_results/{project_name}/下）
    code_root = os.path.dirname(os.path.abspath(__file__))
    scan_results_dir = os.path.join(code_root, "scan_results", args.project_name)
    scan_json = os.path.join(scan_results_dir, args.output)

    # 调用项目总结程序（codesense_project_summarizer.py），新增 --project_path 和 --scenario 参数
    summarizer_cmd = [
        sys.executable, "codesense_project_summarizer.py",
        "--project_name", args.project_name,
        "--scan_json", scan_json,
        "--project_path", args.project_path,
        "--summarizer_config", args.summarizer_config,
        "--output", args.final_summary,
        "--scenario", args.scenario
    ]
    print("正在执行项目总结……")
    ret = subprocess.run(summarizer_cmd)
    if ret.returncode != 0:
        print("项目总结失败，请检查日志。")
        sys.exit(ret.returncode)
    else:
        print("项目总结完成。")
        final_report = os.path.join(scan_results_dir, args.final_summary)
        print(f"最终项目总结报告已生成：{final_report}")

if __name__ == "__main__":
    main()