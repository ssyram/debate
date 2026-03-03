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
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )
    app.config["JSON_AS_ASCII"] = False

    # ── GET / — serve the wizard page ─────────────────────────
    @app.route("/")
    def index():
        return render_template("wizard.html")

    # ── GET /api/defaults — all default values ────────────────
    @app.route("/api/defaults")
    def api_defaults():
        return jsonify(
            title="",
            output_path="",
            rounds=DEFAULT_ROUNDS,
            timeout=DEFAULT_TIMEOUT,
            max_tokens=DEFAULT_MAX_TOKENS,
            base_url="",
            api_key="",
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

    # ── POST /api/generate-stances — LLM stance generation ────
    @app.route("/api/generate-stances", methods=["POST"])
    def api_generate_stances():
        data = request.get_json(silent=True) or {}
        topic_body = data.get("topic_body", "")
        if not topic_body.strip():
            return jsonify(error="议题内容为空"), 400

        result = generate_stances_sync(
            topic_body,
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            model=data.get("model", "gpt-5.2"),
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

    return app


def _extract_config(data: dict[str, Any]) -> dict[str, Any]:
    """Extract a config dict from request JSON, matching generate_topic_file's expected shape."""
    return {
        "title": data.get("title", ""),
        "rounds": int(data.get("rounds", DEFAULT_ROUNDS)),
        "timeout": int(data.get("timeout", DEFAULT_TIMEOUT)),
        "max_tokens": int(data.get("max_tokens", DEFAULT_MAX_TOKENS)),
        "base_url": data.get("base_url", ""),
        "api_key": data.get("api_key", ""),
        "debaters": data.get("debaters", DEFAULT_DEBATERS),
        "judge": data.get("judge", DEFAULT_JUDGE),
        "constraints": data.get("constraints", ""),
        "round1_task": data.get("round1_task", DEFAULT_ROUND1_TASK),
        "middle_task": data.get("middle_task", DEFAULT_MIDDLE_TASK),
        "final_task": data.get("final_task", DEFAULT_FINAL_TASK),
        "judge_instructions": data.get("judge_instructions", DEFAULT_JUDGE_INSTRUCTIONS),
        "topic_body": data.get("topic_body", ""),
    }
