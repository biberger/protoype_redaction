"""Fine-tune a GLiNER2 / GLiNER2.5 checkpoint on a build directory.

    python -m legalner.train data/build/v1 -o out/run1 --base fastino/gliner2.5-multi-v1 --epochs 3

Uses AutoExtractor so boundary (GLiNER2.5) checkpoints load correctly;
gliner2.training.train_gliner2 only loads span checkpoints.
"""
import argparse
import json
import pathlib


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build", help="directory with train.jsonl and dev.jsonl from legalner.build")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--base", default="fastino/gliner2.5-multi-v1")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=-1)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--encoder-lr", type=float, default=1e-5)
    ap.add_argument("--task-lr", type=float, default=5e-4)
    ap.add_argument("--eval-steps", type=int, default=500)
    ap.add_argument("--lora", action="store_true", help="train LoRA adapters instead of full weights")
    ap.add_argument("--wandb", default=None, help="W&B project name (enables W&B logging)")
    ap.add_argument("--precision", choices=["auto", "fp32", "bf16", "fp16"], default="auto",
                    help="auto = trainer default (bf16 for boundary models); fp32 for CPU smoke runs")
    ap.add_argument("--num-workers", type=int, default=4)
    args = ap.parse_args(argv)

    from gliner2 import AutoExtractor
    from gliner2.training import ExtractorTrainer, TrainingConfig

    build = pathlib.Path(args.build)
    config = TrainingConfig(
        output_dir=args.out,
        experiment_name=pathlib.Path(args.out).name,
        num_epochs=args.epochs,
        max_steps=args.max_steps,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        encoder_lr=args.encoder_lr,
        task_lr=args.task_lr,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_best=True,
        early_stopping=True,
        early_stopping_patience=5,
        use_lora=args.lora,
        report_to_wandb=bool(args.wandb),
        wandb_project=args.wandb,
        num_workers=args.num_workers,
        **({} if args.precision == "auto" else
           {"fp16": args.precision == "fp16", "bf16": args.precision == "bf16"}),
    )
    model = AutoExtractor.from_pretrained(args.base)
    trainer = ExtractorTrainer(model=model, config=config)
    result = trainer.train(train_data=str(build / "train.jsonl"), eval_data=str(build / "dev.jsonl"))
    pathlib.Path(args.out, "train_result.json").write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
