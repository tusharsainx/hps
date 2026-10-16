"""Script to render High-Level Design (HLD) and Sequence Diagram PNGs for Paribus HPS."""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, ArrowStyle

DESKTOP_DIR = os.path.expanduser("~/Desktop")
HLD_PATH = os.path.join(DESKTOP_DIR, "paribus_hps_high_level_design.png")
SEQ_PATH = os.path.join(DESKTOP_DIR, "paribus_hps_sequence_diagram.png")


def render_hld():
    """Render High-Level Design (HLD) Architecture Diagram."""
    fig, ax = plt.subplots(figsize=(18, 12), dpi=300)
    fig.patch.set_facecolor("#0b0f19")
    ax.set_facecolor("#0b0f19")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Title Banner
    ax.text(
        50, 96, "Hospital Bulk Processing System (Paribus HPS)",
        ha="center", va="center", color="#ffffff", fontsize=22, fontweight="bold", fontfamily="sans-serif"
    )
    ax.text(
        50, 93, "High-Level Architecture & Hexagonal Ports & Adapters Design",
        ha="center", va="center", color="#94a3b8", fontsize=13, fontfamily="sans-serif"
    )

    # Box Helper Function
    def draw_card(x, y, w, h, title, subtitle="", bg="#121826", border="#2563eb", title_color="#60a5fa"):
        box = FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.8,rounding_size=1.2",
            facecolor=bg, edgecolor=border, linewidth=1.5, zorder=2
        )
        ax.add_patch(box)
        if title:
            ax.text(x + w / 2, y + h - 2.8, title, ha="center", va="center", color=title_color, fontsize=12, fontweight="bold", zorder=3)
        if subtitle:
            ax.text(x + w / 2, y + h - 5.5, subtitle, ha="center", va="center", color="#94a3b8", fontsize=8.5, zorder=3)
        return box

    def draw_component(x, y, w, h, name, desc="", bg="#182234", border="rgba(255,255,255,0.15)", text_color="#f8fafc"):
        box = FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.5,rounding_size=0.8",
            facecolor=bg, edgecolor=border, linewidth=1.0, zorder=4
        )
        ax.add_patch(box)
        ax.text(x + w / 2, y + h / 2 + (1.0 if desc else 0), name, ha="center", va="center", color=text_color, fontsize=10, fontweight="bold", zorder=5)
        if desc:
            ax.text(x + w / 2, y + h / 2 - 1.6, desc, ha="center", va="center", color="#94a3b8", fontsize=7.8, zorder=5)

    def draw_arrow(x1, y1, x2, y2, label="", color="#38bdf8", style="-|>", rad=0.0, dashed=False):
        ls = "--" if dashed else "-"
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle=style, color=color, lw=1.8,
                connectionstyle=f"arc3,rad={rad}", linestyle=ls
            ),
            zorder=6
        )
        if label:
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            ax.text(mx, my + 1.2, label, ha="center", va="center", color="#cbd5e1", fontsize=8, fontweight="bold", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#0b0f19", edgecolor="none", alpha=0.85))

    # 1. Client Layer (Top Left)
    draw_card(4, 76, 22, 14, "CLIENT LAYER", "Interaction Interfaces", border="#8b5cf6", title_color="#c084fc")
    draw_component(6, 82, 18, 3.8, "API Clients / cURL", "Automated Scripts & Ingestion", bg="#1e1b4b", border="#8b5cf6")
    draw_component(6, 77.5, 18, 3.8, "Swagger UI (/docs)", "Interactive OpenAPI Explorer", bg="#1e1b4b", border="#8b5cf6")

    # 2. Ingestion & API Layer
    draw_card(32, 70, 36, 20, "FASTAPI INGESTION & CONTROLLER LAYER", "REST Routing & Background Dispatch", border="#3b82f6", title_color="#60a5fa")
    draw_component(34, 80, 15, 5, "POST /hospitals/bulk", "Fast 202 Accepted (<15ms)", bg="#1e293b", border="#3b82f6")
    draw_component(51, 80, 15, 5, "POST /bulk/validate", "CSV Pre-Validation Diagnostic", bg="#1e293b", border="#3b82f6")
    draw_component(34, 72, 15, 5, "POST /bulk/{id}/resume", "Smart Resume (Delta Retry)", bg="#1e293b", border="#3b82f6")
    draw_component(51, 72, 15, 5, "GET /bulk/{id}", "Real-Time Status & Progress", bg="#1e293b", border="#3b82f6")

    # Connect Client -> API
    draw_arrow(26, 84, 34, 83, "CSV Upload", color="#c084fc")
    draw_arrow(26, 74, 51, 74, "Poll Status", color="#c084fc", rad=0.1)

    # 3. Core Domain & Orchestration Layer
    draw_card(4, 28, 92, 38, "CORE APPLICATION & ORCHESTRATION LAYER", "Business Logic, Concurrency & Resilience", border="#10b981", title_color="#34d399")

    # Services Inside Core
    draw_component(8, 51, 24, 9, "CsvValidator", "• Header schema normalization\n• Max 20 rows limit enforced\n• Row validation (no 413 error)", bg="#064e3b", border="#10b981")
    draw_component(36, 51, 28, 9, "BulkProcessor (Orchestrator)", "• UUID Batch generation\n• Concurrency throttle (Semaphore=10)\n• Atomic Activation & Resume engine", bg="#064e3b", border="#10b981")
    draw_component(68, 51, 24, 9, "HospitalClient (HTTPX)", "• Connection pooling (50 max/20 idle)\n• Exponential backoff retry + jitter\n• Keep-Alive socket reuse", bg="#064e3b", border="#10b981")

    # Connect API -> Core Services
    draw_arrow(41, 70, 20, 60, "Validate CSV", color="#34d399")
    draw_arrow(41, 70, 50, 60, "Dispatch Batch", color="#34d399")
    draw_arrow(32, 55, 36, 55, "Valid Records", color="#34d399")
    draw_arrow(64, 55, 68, 55, "HTTP Calls", color="#34d399")

    # Background Tasks & Heartbeat
    draw_component(36, 32, 28, 12, "Concurrency Controller", "• asyncio.Semaphore(10)\n• Bounded HTTP concurrency\n• Prevents downstream 429s", bg="#172554", border="#3b82f6")
    draw_component(8, 32, 24, 12, "BackgroundTasks Runner", "• Non-blocking async execution\n• Immediate 202 client return\n• Safe background lifecycle", bg="#172554", border="#3b82f6")
    draw_component(68, 32, 24, 12, "Resilience & Heartbeat", "• Retries 502/503/504 errors\n• Keep-alive heartbeat ping\n• Clean rollback / DELETE support", bg="#172554", border="#3b82f6")

    draw_arrow(50, 51, 50, 44, "Throttle", color="#38bdf8")
    draw_arrow(36, 54, 20, 44, "Enqueue Task", color="#38bdf8")

    # 4. Storage & Persistence Ports (Bottom Left)
    draw_card(4, 4, 42, 20, "PORT: STATE REPOSITORY (SOLID)", "Pluggable Storage Layer (BaseBatchRepository)", border="#f59e0b", title_color="#fbbf24")
    draw_component(7, 13, 17, 7, "InMemoryBatchRepo", "Standard Scale\nThread-safe LRU (10k)", bg="#451a03", border="#f59e0b")
    draw_component(26, 13, 17, 7, "Sqlite / Postgres Repo", "Enterprise Scale\nDurable WAL Mode", bg="#451a03", border="#f59e0b")
    ax.text(25, 7.5, "Environment Switch: STORAGE_BACKEND=memory | database", ha="center", color="#fbbf24", fontsize=8.5, fontweight="bold")

    draw_arrow(44, 51, 25, 24, "State & Row Updates", color="#f59e0b", rad=-0.1)

    # 5. External Hospital Directory API (Bottom Right)
    draw_card(54, 4, 42, 20, "EXTERNAL HOSPITAL DIRECTORY API", "Render Deployed Upstream Service", border="#ef4444", title_color="#f87171")
    draw_component(57, 13, 17, 7, "POST /hospitals/", "Create with batch_id\nactive: false", bg="#450a0a", border="#ef4444")
    draw_component(76, 13, 17, 7, "PATCH .../activate", "Atomic Activation\nactive: true", bg="#450a0a", border="#ef4444")
    ax.text(75, 7.5, "URL: https://hospital-directory.onrender.com", ha="center", color="#f87171", fontsize=8.5, fontweight="bold")

    draw_arrow(80, 51, 75, 24, "Outbound Concurrent Requests", color="#f87171")

    # Watermark / Legend
    ax.text(96, 2, "Antigravity IDE • Paribus Python Challenge", ha="right", va="bottom", color="#475569", fontsize=9, fontfamily="monospace")

    plt.tight_layout()
    plt.savefig(HLD_PATH, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"HLD saved to: {HLD_PATH}")


def render_sequence():
    """Render Sequence Diagram PNG."""
    fig, ax = plt.subplots(figsize=(18, 12), dpi=300)
    fig.patch.set_facecolor("#0b0f19")
    ax.set_facecolor("#0b0f19")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Title Banner
    ax.text(
        50, 96, "Hospital Bulk Processing System — Execution Sequence Diagram",
        ha="center", va="center", color="#ffffff", fontsize=22, fontweight="bold", fontfamily="sans-serif"
    )
    ax.text(
        50, 93, "End-to-End CSV Ingestion, Concurrent Creation, Progress Broadcasting & Atomic Batch Activation",
        ha="center", va="center", color="#94a3b8", fontsize=12.5, fontfamily="sans-serif"
    )

    # Lifeline Participants
    actors = [
        {"x": 8, "name": "Client / cURL", "color": "#8b5cf6"},
        {"x": 22, "name": "FastAPI Router", "color": "#3b82f6"},
        {"x": 36, "name": "CsvValidator", "color": "#10b981"},
        {"x": 50, "name": "BatchRepository", "color": "#f59e0b"},
        {"x": 64, "name": "BulkProcessor", "color": "#06b6d4"},
        {"x": 78, "name": "HTTPX Pool (10x)", "color": "#ec4899"},
        {"x": 92, "name": "Upstream API (Render)", "color": "#ef4444"},
    ]

    # Draw Header Boxes and Lifelines
    y_top = 88
    y_bottom = 6

    for a in actors:
        # Header box
        box = FancyBboxPatch(
            (a["x"] - 5.5, y_top), 11, 4.2, boxstyle="round,pad=0.3,rounding_size=0.6",
            facecolor="#182234", edgecolor=a["color"], linewidth=1.5, zorder=5
        )
        ax.add_patch(box)
        ax.text(a["x"], y_top + 2.1, a["name"], ha="center", va="center", color=a["color"], fontsize=9.5, fontweight="bold", zorder=6)

        # Dashed vertical lifeline
        ax.plot([a["x"], a["x"]], [y_top, y_bottom], color="#334155", linestyle="--", lw=1.2, zorder=1)

    # Sequence Messages
    steps = [
        {"step": 1, "from": 8, "to": 22, "y": 83, "label": "1. POST /hospitals/bulk (multipart CSV file)", "color": "#8b5cf6", "dashed": False},
        {"step": 2, "from": 22, "to": 36, "y": 78, "label": "2. validate_and_parse(content_bytes)", "color": "#10b981", "dashed": False},
        {"step": 3, "from": 36, "to": 22, "y": 73, "label": "3. Valid records (<= 20 rows, schema verified)", "color": "#10b981", "dashed": True},
        {"step": 4, "from": 22, "to": 50, "y": 68, "label": "4. create_batch(batch_id=UUID, records)", "color": "#f59e0b", "dashed": False},
        {"step": 5, "from": 22, "to": 64, "y": 63, "label": "5. BackgroundTasks: process_batch(records, batch_id)", "color": "#06b6d4", "dashed": False},
        {"step": 6, "from": 22, "to": 8, "y": 58, "label": "6. Return 202 Accepted (<15ms, batch_id, status: processing)", "color": "#8b5cf6", "dashed": True},

        # Concurrent Creation Loop
        {"step": 7, "from": 64, "to": 78, "y": 50, "label": "7. Concurrent Worker: acquire Semaphore(10)", "color": "#ec4899", "dashed": False},
        {"step": 8, "from": 78, "to": 92, "y": 44, "label": "8. POST /hospitals/ (batch_id, retry backoff)", "color": "#ef4444", "dashed": False},
        {"step": 9, "from": 92, "to": 78, "y": 39, "label": "9. 200 OK: Hospital Created (id, active: false)", "color": "#ef4444", "dashed": True},
        {"step": 10, "from": 78, "to": 50, "y": 34, "label": "10. update_row_success(batch_id, row, id)", "color": "#f59e0b", "dashed": False},

        # Activation Step
        {"step": 11, "from": 64, "to": 92, "y": 27, "label": "11. PATCH /hospitals/batch/{batch_id}/activate", "color": "#ef4444", "dashed": False},
        {"step": 12, "from": 92, "to": 64, "y": 22, "label": "12. 200 OK: Activated count = 20", "color": "#ef4444", "dashed": True},
        {"step": 13, "from": 64, "to": 50, "y": 17, "label": "13. complete_batch(activated=True)", "color": "#f59e0b", "dashed": False},

        # Polling Step
        {"step": 14, "from": 8, "to": 22, "y": 12, "label": "14. Poll: GET /hospitals/bulk/{batch_id}", "color": "#8b5cf6", "dashed": False},
        {"step": 15, "from": 22, "to": 8, "y": 7, "label": "15. Return 200 OK (BatchProgressResponse JSON)", "color": "#8b5cf6", "dashed": True},
    ]

    # Draw Loop Box around Step 8-11
    loop_box = FancyBboxPatch(
        (48, 25), 47, 22, boxstyle="round,pad=0.4,rounding_size=0.8",
        facecolor="#182234", edgecolor="#06b6d4", linewidth=1.2, linestyle=":", alpha=0.35, zorder=2
    )
    ax.add_patch(loop_box)
    ax.text(50, 46, "PARALLEL CONCURRENT WORKERS (Bounded Concurrency = 10, Rate Limit = 25 RPS)", color="#38bdf8", fontsize=8.5, fontweight="bold", zorder=3)

    for s in steps:
        x1 = s["from"]
        x2 = s["to"]
        y = s["y"]
        ls = "--" if s["dashed"] else "-"

        # Arrow
        ax.annotate(
            "", xy=(x2, y), xytext=(x1, y),
            arrowprops=dict(
                arrowstyle="-|>", color=s["color"], lw=1.6,
                linestyle=ls, mutation_scale=12
            ),
            zorder=4
        )

        # Label
        mx = (x1 + x2) / 2
        ax.text(
            mx, y + 1.1, s["label"], ha="center", va="center", color="#f8fafc", fontsize=8.2, fontweight="bold", zorder=5,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#0b0f19", edgecolor=s["color"], alpha=0.9, lw=0.6)
        )

    # Watermark
    ax.text(96, 2, "Antigravity IDE • Paribus Python Challenge", ha="right", va="bottom", color="#475569", fontsize=9, fontfamily="monospace")

    plt.tight_layout()
    plt.savefig(SEQ_PATH, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Sequence diagram saved to: {SEQ_PATH}")


if __name__ == "__main__":
    render_hld()
    render_sequence()
