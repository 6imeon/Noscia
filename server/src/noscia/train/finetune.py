"""Fine-tune the ESG embedder on synthetic pairs — and gate it on the eval.

Phase 2a steps 2–3 (SPEC §7, CLAUDE.md rule 9). Trains Qwen3-Embedding-0.6B on the
``synth.py`` pairs with MultipleNegativesRankingLoss wrapped in MatryoshkaLoss at the
deployed **256-dim** prefix, then re-runs the held-out ESG eval for **base vs
fine-tuned** and prints the verdict. **Ship only if it wins** — this module never
mutates the live index or swaps the model; it produces a candidate + a decision.

**LoRA by default** — a full fine-tune of even a 0.6B model holds weights + grads +
Adam states + activations in memory (≈10 GB+) and OOMs an 18 GB laptop. LoRA trains
only small adapter matrices (optimizer state ~nil), so it fits comfortably in unified
memory with no safety-ceiling override. The adapter is merged into the base before
saving, so the result loads as a plain ``SentenceTransformer``.

The base-vs-FT comparison is in-memory (each model embeds the corpus itself and does
dense top-k), so it isolates the embedder change from the stored Phase-1 vectors.

    uv sync --group train
    uv run --group train python -m noscia.train.finetune --train --compare
    uv run --group train python -m noscia.train.finetune --compare   # eval an existing FT
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..search.embed import MODEL_NAME, QUERY_INSTRUCTION, _pick_device
from ..search.store import EMBED_DIM
from .eval import Report, evaluate, load_eval
from .synth import OUT_PATH as PAIRS_PATH
from .synth import Chunk, fetch_chunks

FT_DIR = Path(__file__).resolve().parents[4] / "data" / "models" / "qwen3-esg-ft"
SHIP_MARGIN = 0.005  # FT must beat base by at least this on nDCG to be worth shipping


def load_pairs(path: Path = PAIRS_PATH):
    import json

    from datasets import Dataset

    if not path.exists():
        raise SystemExit(f"No synthetic pairs at {path}. Run `python -m noscia.train.synth` first.")
    anchors, positives = [], []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        anchors.append(d["query"])
        positives.append(d["positive"])
    return Dataset.from_dict({"anchor": anchors, "positive": positives})


# Attention projections only — the standard, lightest LoRA target set for a decoder.
_LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


def finetune(
    base: str = MODEL_NAME,
    out_dir: Path = FT_DIR,
    epochs: int = 1,
    batch_size: int = 8,
    lr: float = 1e-4,  # LoRA tolerates / wants a higher LR than full fine-tune
    max_seq_length: int = 256,
    lora_r: int = 16,
    lora_alpha: int = 32,
) -> Path:
    from peft import LoraConfig, TaskType
    from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer
    from sentence_transformers.losses import MatryoshkaLoss, MultipleNegativesRankingLoss
    from sentence_transformers.training_args import SentenceTransformerTrainingArguments

    dataset = load_pairs()
    print(f"LoRA fine-tuning on {len(dataset)} pairs ({epochs} epoch(s), batch {batch_size})…")

    model = SentenceTransformer(base, device=_pick_device())
    # Cap sequence length well below Qwen3's native window — activations scale with it,
    # and 256 tokens covers a query + the answering span on an 18 GB box.
    model.max_seq_length = max_seq_length

    # LoRA: only adapter matrices train → optimizer state is tiny. Saved as an adapter
    # on top of the base model and reloaded by SentenceTransformer at eval time.
    model.add_adapter(
        LoraConfig(
            task_type=TaskType.FEATURE_EXTRACTION,
            target_modules=_LORA_TARGETS,
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=0.05,
        )
    )

    # Gradient checkpointing — recompute activations in the backward pass instead of
    # holding all 28 layers' worth. This is the lever that lands training under the
    # MPS memory ceiling on 18 GB (with LoRA + the capped batch/seq above).
    auto_model = model[0].auto_model
    auto_model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    auto_model.enable_input_require_grads()

    # Train at full width; MatryoshkaLoss optimizes the 256-dim prefix we deploy.
    inner = MultipleNegativesRankingLoss(model)
    loss = MatryoshkaLoss(model, inner, matryoshka_dims=[EMBED_DIM])

    args = SentenceTransformerTrainingArguments(
        output_dir=str(out_dir / "_checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        warmup_ratio=0.1,
        fp16=False,  # MPS/CPU-safe; no watermark override
        bf16=False,
        logging_steps=10,
        save_strategy="no",
        report_to=[],
    )
    trainer = SentenceTransformerTrainer(model=model, args=args, train_dataset=dataset, loss=loss)
    trainer.train()

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    print(f"Saved fine-tuned model (base + LoRA adapter) → {out_dir}")
    return out_dir


def _inmemory_retriever(model_path: str, chunks: list[Chunk]):
    """Dense top-k over a corpus this model embeds itself (256-dim, asymmetric)."""
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_path, truncate_dim=EMBED_DIM, device=_pick_device())
    doc_vecs = np.asarray(
        model.encode([c.text for c in chunks], normalize_embeddings=True, batch_size=16)
    )
    urls = [c.url for c in chunks]

    def retrieve(query: str, k: int) -> list[str]:
        qv = np.asarray(
            model.encode(
                [query],
                prompt=f"Instruct: {QUERY_INSTRUCTION}\nQuery: ",
                normalize_embeddings=True,
            )
        )[0]
        order = np.argsort(-(doc_vecs @ qv))
        return [urls[i] for i in order[: max(k * 3, 30)]]

    return retrieve


def compare(base: str = MODEL_NAME, ft_dir: Path = FT_DIR, k: int = 10) -> tuple[Report, Report]:
    if not ft_dir.exists():
        raise SystemExit(f"No fine-tuned model at {ft_dir}. Run with --train first.")
    queries = load_eval()
    chunks = fetch_chunks()
    print(f"Comparing base vs fine-tuned on {len(queries)} queries over {len(chunks)} chunks…")
    base_rep = evaluate("base", _inmemory_retriever(base, chunks), queries, k)
    ft_rep = evaluate("fine-tuned", _inmemory_retriever(str(ft_dir), chunks), queries, k)
    return base_rep, ft_rep


def _verdict(base: Report, ft: Report) -> str:
    wins = (
        ft.ndcg >= base.ndcg + SHIP_MARGIN
        and ft.mrr >= base.mrr - 1e-9
        and ft.recall >= base.recall - 1e-9
    )
    if wins:
        return "SHIP: fine-tuned wins on the ESG eval."
    return (
        "DO NOT SHIP: fine-tuned does not beat base by the margin "
        f"(rule 9). nDCG Δ={ft.ndcg - base.ndcg:+.3f}."
    )


def _report_line(r: Report) -> str:
    return f"  {r.name:<12} nDCG@{r.k}={r.ndcg:.3f}  MRR={r.mrr:.3f}  Recall@{r.k}={r.recall:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Fine-tune the ESG embedder and gate it on eval.")
    ap.add_argument("--train", action="store_true", help="fine-tune on the synthetic pairs")
    ap.add_argument("--compare", action="store_true", help="eval base vs fine-tuned")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    if not (args.train or args.compare):
        ap.error("nothing to do — pass --train and/or --compare")

    if args.train:
        finetune(epochs=args.epochs, batch_size=args.batch_size)

    if args.compare:
        base_rep, ft_rep = compare()
        print("\nESG retrieval eval — base vs fine-tuned:")
        print(_report_line(base_rep))
        print(_report_line(ft_rep))
        print("\n" + _verdict(base_rep, ft_rep))


if __name__ == "__main__":
    main()
