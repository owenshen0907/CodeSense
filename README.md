# CodeSense

CodeSense 是一个用于自动扫描和分析项目代码结构的工具，同时具备项目总结功能。它通过 **项目扫描** 和 **项目总结** 两个核心步骤，为开发者提供完整的代码分析解决方案。

---

## 功能简介

### 1. 项目扫描
- **递归遍历目录**：深度解析项目结构，生成包含文件路径、语言类型、文件类别等信息的 JSON 文件。
- **自定义配置**：
  - **全局配置**：通过 `codesense_config.json` 设置扫描规则（如排除目录、隐藏文件处理）。
  - **项目级配置**：在项目根目录添加 `codesense_project_config.json` 覆盖默认规则。
- **多格式输出**：
  - `project_structure.json`：完整项目结构数据（含预留的 `traversal_order` 和 `summaries` 字段）。
  - `project_tree.md`：Markdown 格式树状目录。
  - `project_files.txt`：文本格式文件路径列表。
- **日志与进度**：自动记录操作日志至 `logs` 目录，并支持断点续跑。

---

### 2. 项目总结
基于扫描结果，CodeSense 提供自动化项目总结能力：
- **初步总结**：自动提取项目根目录的 `readme.md` 作为基础描述，生成标题、功能、技术标签等信息。
- **智能遍历策略**：根据目录结构生成最优遍历顺序，避免大模型上下文溢出。
- **代码摘要生成**：逐文件调用模型生成代码摘要，实时保存进度至 `summarization_progress` 目录。
- **最终报告整合**：合并所有摘要与初步总结，输出包含对比备注的完整项目总结报告。

---

### 3. 自动串联执行
通过 `codesense_run_all.py` 脚本，可一键完成扫描与总结全流程：
```bash
python codesense_run_all.py --project_name "MyProject" --project_path "/path/to/project"
```

---

## 目录结构示例

```plaintext
CodeSense/
├── codesense_scanner.py
├── codesense_project_summarizer.py
├── codesense_run_all.py
├── codesense_config.json
├── codesense_summarizer_config.json
├── model_api_client.py
├── config.ini        # 模型 API 配置文件
├── scan_results/     # 扫描结果存储
│   └── MyProject/
│       ├── project_structure.json
│       ├── project_tree.md
│       └── project_files.txt
├── logs/             # 操作日志记录
└── summarization_progress/  # 生成进度保存
```

---

## 使用方法

### 1. 项目扫描
```bash
python codesense_scanner.py --project_name "MyProject" --path "/path/to/project"
```

### 2. 项目总结
```bash
python codesense_project_summarizer.py --scan_json "scan_results/MyProject/project_structure.json"
```

### 3. 全流程自动执行
```bash
python codesense_run_all.py --project_name "MyProject" --project_path "/path/to/project"
```

---

## 配置说明
- **`codesense_config.json`**：全局扫描规则配置。
- **`codesense_summarizer_config.json`**：总结阶段提示词与模型参数配置。
- **`config.ini`**：模型 API 接入配置（需填写 API Key 与 URL）。

---

## 注意事项
- **断点续跑**：`summarization_progress` 目录保存生成进度，支持中断后继续执行。
- **日志排查**：操作问题可通过 `logs` 目录下的日志文件快速定位。
- **API 优化**：建议在 `config.ini` 中配置高并发 API 调用策略，提升生成效率。

---
