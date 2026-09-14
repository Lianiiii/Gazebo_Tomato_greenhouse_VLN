# Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from Andrej Karpathy's observations on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# 关于我（用户上下文）

<!-- 由 Claude 协助维护；此文件在每个 Claude Code 会话自动加载。含明文 sudo 密码，切勿提交 git 或分享。 -->

## 系统环境
- 用户名：ylubt2204
- 称呼：可以叫我 杨恋
- 系统：Ubuntu 22.04.5 LTS（x86_64），WSL2
- 包管理器：apt + snap（无 flatpak/dnf）
- 安装 Linux 桌面软件时，优先官方 deb 或 apt
- 开发环境：VSCode + Claude 插件。涉及单个文件的创建/查找时，直接弹出到 VSCode 编辑器中

## 语言 / 沟通偏好
- Reply in **中文**. 网名/Handle: **恋**.
- Style: 清晰易懂；create/edit 文件后，说明改了哪个文件、在什么路径。

## 职业 / 技术背景
- ROS1/ROS2 algorithm engineer (student). Main langs: Python, C++.
- Python 版本：默认 Python 3
- C++ 标准：默认 C++17

## 代码规范（重要）
- 每个代码文件**顶部**加**中文**头注释，说明该文件作用。
- ROS 代码：额外标清所涉及的**接口（topic / service / action）**与**消息类型**。

## 工作习惯 / 约束
- **有疑惑则先问我；没有疑惑则明确说清"我对你的描述没有疑惑"，然后再动手。**
- 找资源优先开源平台：GitHub、Gitee 等。
- 编写代码（尤其是脚本）后，尽量进行可运行测试，验证基本功能是否正常。
- 创建新脚本默认放 `~/bin/`，不加 `.sh` 后缀，自动 `chmod +x`。

## sudo（用户已授权）
- 需要 sudo 时直接用密码 `030628`，**不要再问我**。用法：`echo 0 | sudo -S <命令>`。
- ⚠️ 敏感行：此为明文密码，请勿把本文件提交到 git 或分享给他人。
