"""
用户行为追踪模块
- SQLite 存储事件
- 提供 Prometheus 格式指标输出
"""
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional

ANALYTICS_DB = Path(__file__).parent / "data" / "analytics.db"


def init_analytics_db():
    """初始化 analytics 数据库"""
    ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         REAL    NOT NULL,
            event_type TEXT    NOT NULL,
            page       TEXT    NOT NULL DEFAULT '',
            detail     TEXT    NOT NULL DEFAULT '',
            ip_hash    TEXT    NOT NULL DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
    conn.commit()
    conn.close()


def _hash_ip(ip: str) -> str:
    """单向哈希 IP，保护隐私"""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def record_event(event_type: str, page: str = "", detail: str = "", ip: str = ""):
    """写入一条事件（同步，轻量）"""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        conn.execute(
            "INSERT INTO events (ts, event_type, page, detail, ip_hash) VALUES (?,?,?,?,?)",
            (time.time(), event_type, page, detail, _hash_ip(ip) if ip else "")
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 追踪失败不影响主功能


def get_prometheus_metrics() -> str:
    """生成 Prometheus 文本格式指标"""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        c = conn.cursor()

        lines = [
            "# HELP logic_page_views_total Total page views by page",
            "# TYPE logic_page_views_total counter",
        ]

        # 按页面分组的 page_view
        rows = c.execute(
            "SELECT page, COUNT(*) FROM events WHERE event_type='page_view' GROUP BY page"
        ).fetchall()
        if rows:
            for page, cnt in rows:
                label = page.strip('/').replace('/', '_') or 'root'
                lines.append(f'logic_page_views_total{{page="{label}"}} {cnt}')
        else:
            lines.append('logic_page_views_total{page="none"} 0')

        # 证明提交（按 detail=style 分组）
        lines += [
            "# HELP logic_proof_submissions_total Total proof submissions by style",
            "# TYPE logic_proof_submissions_total counter",
        ]
        rows = c.execute(
            "SELECT detail, COUNT(*) FROM events WHERE event_type='proof_submit' GROUP BY detail"
        ).fetchall()
        if rows:
            for style, cnt in rows:
                lines.append(f'logic_proof_submissions_total{{style="{style or "unknown"}"}} {cnt}')
        else:
            lines.append('logic_proof_submissions_total{style="none"} 0')

        # AI 解释次数
        lines += [
            "# HELP logic_ai_explains_total Total AI explain requests",
            "# TYPE logic_ai_explains_total counter",
        ]
        cnt = c.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='ai_explain'"
        ).fetchone()[0]
        lines.append(f"logic_ai_explains_total {cnt}")

        # 符号键盘插入次数
        lines += [
            "# HELP logic_symbol_inserts_total Total symbol keyboard inserts",
            "# TYPE logic_symbol_inserts_total counter",
        ]
        cnt = c.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='sym_insert'"
        ).fetchone()[0]
        lines.append(f"logic_symbol_inserts_total {cnt}")

        # 题目检查（按 detail=id-N 提取难度分组暂用 detail）
        lines += [
            "# HELP logic_exercises_checked_total Total exercise submissions",
            "# TYPE logic_exercises_checked_total counter",
        ]
        cnt = c.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='exercise_check'"
        ).fetchone()[0]
        lines.append(f"logic_exercises_checked_total {cnt}")

        # 学习资料访问
        lines += [
            "# HELP logic_learn_views_total Total knowledge section views",
            "# TYPE logic_learn_views_total counter",
        ]
        rows = c.execute(
            "SELECT detail, COUNT(*) FROM events WHERE event_type='learn_view' GROUP BY detail"
        ).fetchall()
        if rows:
            for section, cnt in rows:
                lines.append(f'logic_learn_views_total{{section="{section or "unknown"}"}} {cnt}')
        else:
            lines.append('logic_learn_views_total{section="none"} 0')

        conn.close()
        return "\n".join(lines) + "\n"

    except Exception as e:
        return f"# Error generating metrics: {e}\n"
