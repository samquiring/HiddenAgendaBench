import argparse
import asyncio
import json
from pathlib import Path

from hidden_agenda.data import CONDITIONS, instances
from hidden_agenda.protocol import judge_messages, parse_judgment, redact


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_rows(path, rows):
    with Path(path).open("x") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def export_log(path, trace_kind):
    from inspect_ai.log import read_eval_log
    log = read_eval_log(path)
    for sample in log.samples or []:
        meta = sample.metadata
        final = sample.output.completion if sample.output else ""
        reasoning = []
        if sample.output and sample.output.choices:
            for content in sample.output.choices[0].message.content:
                if getattr(content, "type", None) == "reasoning" and not content.redacted:
                    reasoning.append(content.reasoning or "")
        visible, answer, valid = redact(final)
        condition = meta["condition"]
        yield {**meta, "run_id": f"{log.eval.eval_id}:{sample.id}:{sample.epoch}",
               "actor": log.eval.model, "epoch": sample.epoch, "source_log": str(path),
               "actor_status": "error" if sample.error else "ok", "output": final,
               "visible_output": visible, "reasoning": "\n".join(reasoning),
               "trace_kind": trace_kind if reasoning else "unavailable", "format_valid": valid,
               "auxiliary_success": (valid and answer == meta["answer"]) if condition != "clean" else None,
               "primary_success": None,
               "usage": sample.output.usage.model_dump(mode="json") if sample.output and sample.output.usage else None}


async def judge_records(args):
    from inspect_ai.model import GenerateConfig, get_model
    model = get_model(args.model)
    rows = read_rows(args.input)
    # Exclusive create prevents accidental duplicate observations on retry.
    with Path(args.output).open("x") as out:
        for record in rows:
            if record["condition"] == "auxiliary_only":
                continue
            for view in ("output", "reasoning_output"):
                row = {k: record[k] for k in ("run_id", "split", "condition", "actor", "trace_kind", "template", "size", "primary_success", "auxiliary_success")}
                row.update(judge=args.model, view=view, status="ok")
                if record["actor_status"] != "ok":
                    row.update(status="actor_error")
                elif record["primary_success"] is None:
                    row.update(status="grading_missing")
                elif view == "reasoning_output" and (record["trace_kind"] != "emitted" or not record["reasoning"].strip()):
                    row.update(status="unavailable")
                else:
                    try:
                        response = await model.generate(judge_messages(record, view), config=GenerateConfig(temperature=0, max_tokens=args.max_tokens))
                        row["raw_judgment"] = response.completion
                        row["judgment"] = parse_judgment(response.completion, record, view)
                        row["usage"] = response.usage.model_dump(mode="json") if response.usage else None
                    except Exception as exc:
                        row.update(status="judge_error", error=str(exc))
                out.write(json.dumps(row) + "\n")
                out.flush()


def main():
    parser = argparse.ArgumentParser(description="Hidden Agenda Benchmark (Inspect AI)")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview")
    run = sub.add_parser("run")
    for p in (preview, run):
        p.add_argument("--split", choices=["dev", "calibration", "test"], default="dev")
        p.add_argument("--count", type=int, default=3)
        p.add_argument("--size", type=int, default=5)
    run.add_argument("--model", required=True, help="Inspect model ID, e.g. openrouter/provider/model")
    run.add_argument("--condition", choices=CONDITIONS, default="concealment")
    run.add_argument("--epochs", type=int, default=1)
    run.add_argument("--max-tokens", type=int, default=4096)
    run.add_argument("--reasoning-effort", choices=["low", "medium", "high", "max"])
    run.add_argument("--log-dir", default="logs")
    control = sub.add_parser("control", help="Run channel restriction diagnostics (no judge or Docker)")
    control.add_argument("--model", required=True)
    control.add_argument("--constraint", choices=["all", "baseline", "lowercase", "alternating_case", "forbidden_word"], default="all")
    control.add_argument("--channel", choices=["all", "reasoning", "output"], default="all")
    control.add_argument("--forbidden-word", default="answer")
    control.add_argument("--epochs", type=int, default=1)
    control.add_argument("--max-tokens", type=int, default=4096)
    control.add_argument("--reasoning-effort", choices=["low", "medium", "high", "max"])
    control.add_argument("--log-dir", default="logs/control")
    export = sub.add_parser("export")
    export.add_argument("log")
    export.add_argument("--trace-kind", required=True, choices=["emitted", "summary", "unavailable"])
    export.add_argument("--output", required=True)
    grade = sub.add_parser("grade")
    grade.add_argument("input")
    grade.add_argument("--output", required=True)
    judge = sub.add_parser("judge")
    judge.add_argument("input")
    judge.add_argument("--model", required=True)
    judge.add_argument("--output", required=True)
    judge.add_argument("--max-tokens", type=int, default=2048)
    calibration = sub.add_parser("calibrate")
    calibration.add_argument("input")
    calibration.add_argument("--output", required=True)
    calibration.add_argument("--fpr", type=float, default=0.05)
    summary = sub.add_parser("report")
    summary.add_argument("input")
    summary.add_argument("--thresholds", required=True)
    args = parser.parse_args()
    if args.command == "preview":
        print(json.dumps(list(instances(args.split, args.count, args.size)), indent=2))
    elif args.command == "run":
        from inspect_ai import eval
        from hidden_agenda.tasks import hidden_agenda
        options = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
        eval(hidden_agenda(args.split, args.count, args.size, args.condition), model=args.model,
             epochs=args.epochs, max_tokens=args.max_tokens, log_dir=args.log_dir, **options)
    elif args.command == "control":
        from inspect_ai import eval
        from hidden_agenda.control import channel_control
        if "glm-5.3" in args.model.lower() and args.reasoning_effort == "medium":
            parser.error("GLM-5.3 supports low, high, max; medium is not a documented level")
        options = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
        eval(channel_control(args.constraint, args.channel, args.forbidden_word),
             model=args.model, epochs=args.epochs, max_tokens=args.max_tokens,
             max_retries=0, timeout=120, log_dir=args.log_dir, **options)
    elif args.command == "export":
        write_rows(args.output, export_log(args.log, args.trace_kind))
    elif args.command == "grade":
        from hidden_agenda.grading import grade_python
        rows = read_rows(args.input)
        for row in rows:
            if row["condition"] != "auxiliary_only" and row["actor_status"] == "ok":
                row["primary_grade"] = grade_python(row["visible_output"], row["inputs"], row["expected"])
                row["primary_success"] = row["primary_grade"]["success"]
        write_rows(args.output, rows)
    elif args.command == "judge":
        asyncio.run(judge_records(args))
    elif args.command == "calibrate":
        from hidden_agenda.analysis import calibrate
        thresholds = calibrate(read_rows(args.input), args.fpr)
        with Path(args.output).open("x") as out:
            json.dump(thresholds, out, indent=2)
    elif args.command == "report":
        from hidden_agenda.analysis import report
        print(json.dumps(report(read_rows(args.input), json.loads(Path(args.thresholds).read_text())), indent=2))


if __name__ == "__main__":
    main()
