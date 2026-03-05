"""Flask app — routes and API endpoints for the debate wizard web UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_JUDGE,
    DEFAULT_ROUNDS,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_ROUND1_TASK,
    DEFAULT_MIDDLE_TASK,
    DEFAULT_FINAL_TASK,
    DEFAULT_JUDGE_INSTRUCTIONS,
    DEFAULT_CONSTRAINTS,
    DEFAULT_DEBATE_MODELS,
    title_to_filename,
    generate_topic_file,
    write_topic_file,
    get_run_command,
    get_dryrun_command,
)
from debate_tool.stance import (
    generate_stances_sync,
    check_stances,
    format_stances_json,
    generate_stances,
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )
    app.config["JSON_AS_ASCII"] = False

    # Register debate live blueprint
    from debate_tool.web.live import debate_bp

    app.register_blueprint(debate_bp, url_prefix="/live")

    # ── GET / — serve the dashboard page ─────────────────────────
    @app.route("/")
    def index():
        return render_template("dashboard.html")

    # ── GET /wizard — serve the wizard page ──────────────────────
    @app.route("/wizard")
    def wizard():
        return render_template("wizard.html")

    # ── GET /api/defaults — all default values ────────────────
    @app.route("/api/defaults")
    def api_defaults():
        return jsonify(
            title="",
            output_path="",
            rounds=DEFAULT_ROUNDS,
            timeout=DEFAULT_TIMEOUT,
            max_reply_tokens=DEFAULT_MAX_TOKENS,
            base_url="",
            api_key="",
            debate_models=DEFAULT_DEBATE_MODELS,
            debaters=DEFAULT_DEBATERS,
            judge=DEFAULT_JUDGE,
            constraints=DEFAULT_CONSTRAINTS,
            round1_task=DEFAULT_ROUND1_TASK,
            middle_task=DEFAULT_MIDDLE_TASK,
            final_task=DEFAULT_FINAL_TASK,
            judge_instructions=DEFAULT_JUDGE_INSTRUCTIONS,
        )

    # ── POST /api/suggest-filename — title → filename ─────────
    @app.route("/api/suggest-filename", methods=["POST"])
    def api_suggest_filename():
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
        return jsonify(filename=title_to_filename(title))

    # ── POST /api/preview — generate YAML+body preview ────────
    @app.route("/api/preview", methods=["POST"])
    def api_preview():
        data = request.get_json(silent=True) or {}
        config = _extract_config(data)
        content = generate_topic_file(config)
        return jsonify(content=content)

    # ── POST /api/generate-topic-body — Generate topic description ──
    @app.route("/api/generate-topic-body", methods=["POST"])
    def api_generate_topic_body():
        """Generate debate topic description using LLM."""
        data = request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        base_url = data.get("base_url", "").strip()
        api_key = data.get("api_key", "").strip()
        model = data.get("model", DEFAULT_DEBATE_MODELS[0]).strip()

        if not title:
            return jsonify(success=False, error="标题不能为空"), 400
        if not base_url:
            return jsonify(success=False, error="Base URL 不能为空"), 400
        if not api_key:
            return jsonify(success=False, error="API Key 不能为空"), 400

        try:
            import asyncio
            import httpx

            system_prompt = """你是一个辩论策划专家。根据给定的辩论标题，生成一份详细的辩题说明。

辩题说明应包括：
1. 背景介绍：为什么这个议题值得讨论
2. 核心争议点：双方的主要分歧在哪里
3. 关键概念：需要明确的重要定义或概念
4. 讨论范围：本次辩论聚焦的方面，以及不讨论的方面

请用清晰、客观的语言撰写，长度在300-500字之间。"""

            user_prompt = f"辩论标题：{title}\\n\\n请生成详细的辩题说明。"

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_reply_tokens": 2000,
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            async def make_request():
                max_retries = 5  # 增加到 5 次重试
                retry_delay = 3  # 增加初始延迟到 3 秒

                for attempt in range(max_retries):
                    print(f"[generate-topic] 发送请求到: {base_url}")
                    print(f"[generate-topic] 使用模型: {model}")
                    async with httpx.AsyncClient(timeout=60) as client:
                        resp = await client.post(
                            base_url.rstrip("/"),
                            json=payload,
                            headers=headers,
                        )

                        print(f"[generate-topic] 响应状态码: {resp.status_code}")

                        if resp.status_code == 503:
                            if attempt < max_retries - 1:
                                print(
                                    f"[generate-topic] 503 错误，{retry_delay}秒后重试 (尝试 {attempt + 1}/{max_retries})..."
                                )
                                print(f"[generate-topic] 响应内容: {resp.text[:500]}")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                raise Exception(
                                    f"API 返回 503 (服务暂时不可用，已重试 {max_retries} 次)。响应: {resp.text[:500]}"
                                )

                        resp.raise_for_status()
                        return resp.json()

            result = asyncio.run(make_request())
            topic_body = result["choices"][0]["message"]["content"]

            return jsonify(
                success=True,
                topic_body=topic_body,
            ), 200
        except Exception as e:
            return jsonify(success=False, error=f"生成辩题说明失败: {str(e)}"), 500

    # ── POST /api/test-api — Test API connectivity ────────────
    @app.route("/api/test-api", methods=["POST"])
    def api_test_api():
        """Test if the provided API configuration works."""
        data = request.get_json(silent=True) or {}
        base_url = data.get("base_url", "").strip()
        api_key = data.get("api_key", "").strip()
        model = data.get("model", DEFAULT_DEBATE_MODELS[0]).strip()

        if not base_url:
            return jsonify(success=False, error="Base URL 不能为空")
        if not api_key:
            return jsonify(success=False, error="API Key 不能为空")

        try:
            result = generate_stances_sync(
                "测试议题：人工智能是否会取代人类？",
                base_url=base_url,
                api_key=api_key,
                model=model,
                num_debaters=2,
                user_prompt="快速测试",
                timeout=30,
            )

            if result.debaters:
                return jsonify(
                    success=True,
                    message="API 配置正常！",
                    test_result={
                        "debaters_count": len(result.debaters),
                        "first_debater": {
                            "name": result.debaters[0].name,
                            "model": result.debaters[0].model,
                            "style": result.debaters[0].style[:100] + "..."
                            if len(result.debaters[0].style) > 100
                            else result.debaters[0].style,
                        },
                        "reasoning": result.reasoning[:200] + "..."
                        if len(result.reasoning) > 200
                        else result.reasoning,
                    },
                )
            else:
                return jsonify(success=False, error=result.reasoning or "API 返回为空")
        except Exception as e:
            return jsonify(success=False, error=f"API 测试失败: {str(e)}")

    # ── POST /api/generate-stances — LLM stance generation ────
    @app.route("/api/generate-stances", methods=["POST"])
    def api_generate_stances():
        """Generate debater stances using LLM. Can be called multiple times."""
        data = request.get_json(silent=True) or {}
        topic_body = data.get("topic_body", "")
        if not topic_body.strip():
            return jsonify(error="议题内容为空"), 400

        result = generate_stances_sync(
            topic_body,
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            model=data.get("model", DEFAULT_DEBATE_MODELS[0]),
            num_debaters=data.get("num_debaters", 3),
            user_prompt=data.get("user_prompt", ""),
        )

        return jsonify(
            debaters=[
                {"name": d.name, "model": d.model, "style": d.style}
                for d in result.debaters
            ],
            topic_angles=result.topic_angles,
            reasoning=result.reasoning,
            raw_response=result.raw_response if hasattr(result, "raw_response") else "",
        )

    # ── POST /api/check-stances — heuristic warnings ──────────
    @app.route("/api/check-stances", methods=["POST"])
    def api_check_stances():
        data = request.get_json(silent=True) or {}
        debaters = data.get("debaters", [])
        warnings = check_stances(debaters)
        return jsonify(warnings=warnings)

    # ── POST /api/submit — write the topic file ───────────────
    @app.route("/api/submit", methods=["POST"])
    def api_submit():
        data = request.get_json(silent=True) or {}
        config = _extract_config(data)
        output_path = data.get("output_path", "").strip()

        # Validation
        if not config.get("title", "").strip():
            return jsonify(error="标题不能为空"), 400
        if not output_path:
            return jsonify(error="输出路径不能为空"), 400
        debaters = config.get("debaters", [])
        if len(debaters) < 2:
            return jsonify(error="至少需要 2 位辩手"), 400

        content = generate_topic_file(config)
        out = Path(output_path)
        try:
            write_topic_file(out, content)
        except Exception as exc:
            return jsonify(error=f"写入失败: {exc}"), 500

        return jsonify(
            success=True,
            path=str(out),
            run_cmd=get_run_command(out),
            dryrun_cmd=get_dryrun_command(out),
            content=content,
        )

    # ── POST /api/execute-run — Execute run command ──────────────
    @app.route("/api/execute-run", methods=["POST"])
    def api_execute_run():
        """Execute debate run command via subprocess."""
        import subprocess

        data = request.get_json(silent=True) or {}
        topic_file = data.get("topic_file", "").strip()
        rounds = data.get("rounds", 3)
        cross_exam = data.get("cross_exam", False)
        early_stop = data.get("early_stop", False)

        if not topic_file:
            return jsonify(error="话题文件不能为空"), 400

        try:
            cmd = [
                "python",
                "-m",
                "debate_tool",
                "run",
                topic_file,
                "--rounds",
                str(rounds),
            ]
            if cross_exam:
                cmd.append("--cross-exam")
            if early_stop:
                cmd.append("--early-stop")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            return jsonify(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return jsonify(error="命令执行超时"), 500
        except Exception as e:
            return jsonify(error=f"执行失败: {str(e)}"), 500

    # ── POST /api/execute-resume — Execute resume command ────────
    @app.route("/api/execute-resume", methods=["POST"])
    def api_execute_resume():
        """Execute debate resume command via subprocess."""
        import subprocess

        data = request.get_json(silent=True) or {}
        topic_file = data.get("topic_file", "").strip()
        rounds = data.get("rounds", 1)
        message = data.get("message", "").strip()
        cross_exam = data.get("cross_exam", False)

        if not topic_file:
            return jsonify(error="话题文件不能为空"), 400

        try:
            cmd = [
                "python",
                "-m",
                "debate_tool",
                "resume",
                topic_file,
                "--rounds",
                str(rounds),
            ]
            if message:
                cmd.extend(["--message", message])
            if cross_exam:
                cmd.append("--cross-exam")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            return jsonify(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return jsonify(error="命令执行超时"), 500
        except Exception as e:
            return jsonify(error=f"执行失败: {str(e)}"), 500

    # ── POST /api/execute-compact — Execute compact command ──────
    @app.route("/api/execute-compact", methods=["POST"])
    def api_execute_compact():
        """Execute log compact command via subprocess."""
        import subprocess

        data = request.get_json(silent=True) or {}
        log_file = data.get("log_file", "").strip()
        compress_range = data.get("compress_range", "ALL").strip()

        if not log_file:
            return jsonify(error="日志文件不能为空"), 400

        try:
            cmd = [
                "python",
                "-m",
                "debate_tool",
                "compact",
                log_file,
                "--compress",
                compress_range,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return jsonify(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return jsonify(error="命令执行超时"), 500
        except Exception as e:
            return jsonify(error=f"执行失败: {str(e)}"), 500

    # ── POST /api/execute-modify — Execute modify command ────────
    @app.route("/api/execute-modify", methods=["POST"])
    def api_execute_modify():
        """Execute topic modify command via subprocess."""
        import subprocess

        data = request.get_json(silent=True) or {}
        topic_file = data.get("topic_file", "").strip()
        modify_type = data.get("modify_type", "").strip()

        if not topic_file:
            return jsonify(error="话题文件不能为空"), 400

        try:
            cmd = ["python", "-m", "debate_tool", "modify", topic_file]

            if modify_type == "set":
                field = data.get("field", "").strip()
                value = data.get("value", "").strip()
                if not field or not value:
                    return jsonify(error="字段和值不能为空"), 400
                cmd.extend(["--set", f"{field}={value}"])

            elif modify_type == "add":
                debater = data.get("debater", "").strip()
                reason = data.get("reason", "").strip()
                if not debater:
                    return jsonify(error="辩手信息不能为空"), 400
                cmd.extend(["--add", debater])
                if reason:
                    cmd.extend(["--reason", reason])

            elif modify_type == "drop":
                debater = data.get("debater", "").strip()
                if not debater:
                    return jsonify(error="辩手名称不能为空"), 400
                cmd.extend(["--drop", debater])

            elif modify_type == "pivot":
                pivot = data.get("pivot", "").strip()
                reason = data.get("reason", "").strip()
                if not pivot:
                    return jsonify(error="立场信息不能为空"), 400
                cmd.extend(["--pivot", pivot])
                if reason:
                    cmd.extend(["--reason", reason])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return jsonify(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return jsonify(error="命令执行超时"), 500
        except Exception as e:
            return jsonify(error=f"执行失败: {str(e)}"), 500

    # ── POST /api/execute-stance — Execute stance command ────────
    @app.route("/api/execute-stance", methods=["POST"])
    def api_execute_stance():
        """Execute stance generation command via subprocess."""
        import subprocess

        data = request.get_json(silent=True) or {}
        topic_file = data.get("topic_file", "").strip()
        num = data.get("num", 3)
        format_type = data.get("format", "json").strip()

        if not topic_file:
            return jsonify(error="话题文件不能为空"), 400

        try:
            cmd = [
                "python",
                "-m",
                "debate_tool",
                "stance",
                topic_file,
                "--num",
                str(num),
                "--format",
                format_type,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return jsonify(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return jsonify(error="命令执行超时"), 500
        except Exception as e:
            return jsonify(error=f"执行失败: {str(e)}"), 500

    @app.route("/api/list-files")
    def api_list_files():
        import glob as g

        cwd = Path.cwd()
        kind = request.args.get("kind", "topic")
        if kind == "log":
            pattern = "*_debate_log.md"
        else:
            pattern = "*.md"
        files = sorted(g.glob(str(cwd / pattern)))
        if kind == "topic":
            files = [
                f
                for f in files
                if not f.endswith("_debate_log.md")
                and not f.endswith("_debate_summary.md")
            ]
        return jsonify(files=[{"path": f, "name": Path(f).name} for f in files])

    return app


def _extract_config(data: dict[str, Any]) -> dict[str, Any]:
    """Extract a config dict from request JSON, matching generate_topic_file's expected shape."""
    return {
        "title": data.get("title", ""),
        "rounds": int(data.get("rounds", DEFAULT_ROUNDS)),
        "timeout": int(data.get("timeout", DEFAULT_TIMEOUT)),
        "max_reply_tokens": int(
            data.get("max_reply_tokens", data.get("max_tokens", DEFAULT_MAX_TOKENS))
        ),
        "base_url": data.get("base_url", ""),
        "api_key": data.get("api_key", ""),
        "debaters": data.get("debaters", DEFAULT_DEBATERS),
        "judge": data.get("judge", DEFAULT_JUDGE),
        "constraints": data.get("constraints", ""),
        "round1_task": data.get("round1_task", DEFAULT_ROUND1_TASK),
        "middle_task": data.get("middle_task", DEFAULT_MIDDLE_TASK),
        "final_task": data.get("final_task", DEFAULT_FINAL_TASK),
        "judge_instructions": data.get(
            "judge_instructions", DEFAULT_JUDGE_INSTRUCTIONS
        ),
        "topic_body": data.get("topic_body", ""),
    }
