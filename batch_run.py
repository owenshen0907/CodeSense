import os
import sys
import subprocess

# 定义需要分析的项目及其路径（相对于当前脚本所在目录）
projects = [
    {"name": "OpenManus", "path": "../../OpenManus"},
    {"name": "yolov5",   "path": "../../yolov5"},
    # {"name": "dify",     "path": "../../dify"},
    # {"name": "tensorflow", "path": "../../tensorflow"},
    {"name": "LLaMA-Factory", "path": "../../LLaMA-Factory"}
    # {"name": "diffusers", "path": "../../diffusers"},
    # {"name": "peft", "path": "../../peft"}
]

# scenario 参数统一为 "direct"
scenario = "direct"

def run_project(project):
    cmd = [
        sys.executable, "codesense_run_all.py",
        "--project_name", project["name"],
        "--project_path", project["path"],
        "--scenario", scenario
    ]
    print(f"正在处理项目：{project['name']}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"项目 {project['name']} 分析失败，退出。")
        sys.exit(result.returncode)
    else:
        print(f"项目 {project['name']} 分析完成。\n")

def main():
    for project in projects:
        run_project(project)
    print("所有项目分析完成。")

if __name__ == "__main__":
    main()