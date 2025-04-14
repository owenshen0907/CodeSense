
# CodeSense

CodeSense 是一个用于自动扫描与分析项目代码结构的工具，同时具备智能项目总结功能。该工具提供两大核心步骤：**项目扫描** 和 **项目总结**，能够为开发者生成完整的代码结构分析报告及定制化的项目说明。

---

## 环境搭建

推荐通过 `conda` 创建独立环境，确保各模块依赖的兼容性：

```bash
conda create -n codeSense python=3.12.4
conda activate codeSense
```

安装项目依赖：

```bash
pip install -r requirements.txt
```

**配置文件**：确保 `config.ini` 中正确填写了大模型 API 的 Key、URL 等参数。

---

## 主要功能介绍

### 1. 项目扫描
**项目扫描** 模块负责自动遍历项目目录，递归分析文件结构，生成项目详细的结构数据和辅助输出文件。

- **递归目录遍历**  
  自动分析所有文件及目录，记录路径、语言类型、文件类别、字符数、是否需要遍历（`need_traverse`）等信息。
  
- **配置支持**  
  - **全局配置**：通过 `codesense_config.json` 定义扫描规则（如排除目录、隐藏文件处理等）。  
  - **项目级配置**：在项目根目录添加 `codesense_project_config.json` 覆盖全局设置。

- **多格式输出**  
  - `project_structure.json`：保存项目结构数据（含预留字段 `summaries` 等）。  
  - `project_tree.md`：Markdown 格式的目录树。  
  - `project_files.txt`：所有文件相对路径列表。

- **日志与断点续跑**  
  扫描过程记录详细日志至 `logs` 目录，支持异常时断点续跑。

---

### 2. 项目总结
**项目总结** 利用扫描结果，通过调用大模型 API 对代码文件生成摘要，并结合原始 README 生成最终报告。

#### 场景说明
CodeSense 提供以下模式满足不同需求：

| 场景       | 用途                                                                 | 特点                                                                 | 配置项                  | 输出文件名示例           |
|------------|----------------------------------------------------------------------|----------------------------------------------------------------------|-------------------------|--------------------------|
| **direct** | 生成全新 README，不参考原始文件                                     | 简单明了，基于代码摘要                                               | `"use_initial_readme": false` | `direct_readme.md`      |
| **correct**| 对原始 README 进行纠正，指出不足并给出建议                          | 整合原始 README 与代码摘要，便于对比修改                             | `"use_initial_readme": true`  | `correct_readme.md`     |
| **usage**  | 生成使用说明和开发指引                                              | 详细描述安装步骤、使用方法、常见问题                                 | `"use_initial_readme": true`  | `usage_instructions.md` |
| **custom** | 自定义总结样式，支持用户自定义提示词                                | 灵活控制是否参考原始 README，提示词完全由用户设置                   | `"use_initial_readme": false` | `custom_readme.md`      |

**输出文件命名规则**：最终文件名包含场景标识和时间戳（如 `direct_readme_20250415_023456.md`）。

---

### 3. 自动执行全流程
通过 `codesense_run_all.py` 脚本一键完成扫描与总结：

```bash
python codesense_run_all.py --project_name "MyProject" --project_path "/path/to/MyProject" --scenario direct
```

运行后：
- 生成项目结构文件、Markdown 目录树和文件列表。  
- 根据所选场景生成最终项目总结报告。

---

## 目录结构示例

```text
CodeSense/
├── codesense_scanner.py              # 项目扫描工具
├── codesense_project_summarizer.py   # 项目总结工具（支持多种场景）
├── codesense_run_all.py              # 一键自动执行扫描与总结
├── codesense_config.json             # 扫描全局配置
├── codesense_summarizer_config.json  # 项目总结配置（含各场景提示词与 md_path 配置）
├── model_api_client.py               # 模型 API 客户端
├── config.ini                        # 模型 API 配置文件
├── scan_results/                     # 扫描结果和最终报告存储目录
│   └── MyProject/
│       ├── project_structure.json   # 项目结构数据
│       ├── project_tree.md          # Markdown 目录树
│       ├── project_files.txt        # 文件列表
│       └── direct_readme_20250415_023456.md  # 示例：direct 模式生成的总结报告
└── logs/                             # 操作日志记录
```

---

## 配置说明
- **`codesense_config.json`**  
  设置项目扫描规则，包括文件类型、排除目录、二进制文件后缀等。

- **`codesense_summarizer_config.json`**  
  定义项目总结阶段的提示词及参数。各场景配置示例：
  ```json
  {
    "scenarios": {
      "direct": {
        "use_initial_readme": false,
        "final_summary_prompt": "...",
        "batch_summary_prompt": "..."
      },
      "correct": {
        "use_initial_readme": true,
        "final_summary_prompt": "...",
        "batch_summary_prompt": "..."
      }
    }
  }
  ```

- **`config.ini`**  
  配置大模型 API 参数（如 API Key、请求 URL 等）。

---

## 注意事项
- **日志排查**：所有操作日志记录于 `logs` 目录。  
- **断点续跑**：扫描和总结过程支持异常中断后继续操作。  
- **提示词定制**：修改 `codesense_summarizer_config.json` 中的提示词模板。  
- **API 调用**：确保 `config.ini` 中正确配置 API 参数。

---

## 联系与支持
如有问题，请联系项目负责人或提交 Issue 至项目仓库。
```