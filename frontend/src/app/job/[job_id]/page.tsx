"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { CheckCircle2, XCircle } from "lucide-react";

const STAGES = ["queued", "cloning", "embedding", "writing_results", "done", "error"];

const STAGE_LABELS: Record<string, string> = {
  queued:          "Queued",
  cloning:         "Cloning",
  embedding:       "Embedding",
  writing_results: "Saving",
  done:            "Done",
  error:           "Error",
};

type LogLine = { ts: string; text: string; isError?: boolean };

export default function JobTracker() {
  const { job_id } = useParams();
  const router = useRouter();

  const [status, setStatus] = useState("queued");
  const [stage, setStage] = useState("queued");
  const [message, setMessage] = useState("Initializing worker…");
  const [errorMsg, setErrorMsg] = useState("");
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [progress, setProgress] = useState(5);
  const logEndRef = useRef<HTMLDivElement>(null);

  const addLog = (text: string, isError = false) => {
    const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
    setLogs((prev) => [...prev, { ts, text, isError }]);
  };

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    if (!job_id) return;

    addLog("Connecting to worker…");

    const eventSource = new EventSource(`http://127.0.0.1:8000/api/jobs/${job_id}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setStatus(data.status);
        setStage(data.stage);
        setMessage(data.message);

        // Update progress bar
        const idx = STAGES.indexOf(data.stage);
        if (data.status === "done") {
          setProgress(100);
        } else if (idx !== -1) {
          setProgress(Math.max(10, Math.round((idx / (STAGES.length - 2)) * 100)));
        }

        addLog(data.message, data.status === "error");

        if (data.status === "error") {
          setErrorMsg(data.error || data.message || "An unknown error occurred.");
          eventSource.close();
        }

        if (data.status === "done") {
          eventSource.close();
          addLog("Redirecting to dashboard…");
          setTimeout(() => router.push(`/dashboard/${data.snapshot_id}`), 1200);
        }
      } catch (err) {
        console.error("Failed to parse SSE message", err);
      }
    };

    eventSource.onerror = () => {
      setStatus("error");
      setErrorMsg("Lost connection or stream ended unexpectedly.");
      addLog("Connection lost.", true);
      eventSource.close();
    };

    return () => eventSource.close();
  }, [job_id, router]);

  const stageList = STAGES.slice(0, -1); // exclude "error" from stage pills
  const activeIdx = stageList.indexOf(stage);

  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center p-6"
      style={{ background: "var(--ra-bg)" }}
    >
      {/* Top progress bar */}
      <div
        className="fixed top-0 left-0 right-0 h-0.5 transition-all duration-500 z-50"
        style={{
          width: `${progress}%`,
          background: status === "error" ? "var(--ra-red)" : "var(--ra-accent)",
          boxShadow: status === "error"
            ? "0 0 8px rgba(255,77,109,0.5)"
            : "0 0 8px var(--ra-accent-glow)",
        }}
      />
      <div
        className="fixed top-0 left-0 right-0 h-0.5 z-40"
        style={{ background: "var(--ra-border)" }}
      />

      <div className="w-full max-w-xl space-y-6 animate-fade-up">

        {/* Stage pills */}
        <div className="flex items-center gap-0">
          {stageList.map((s, i) => {
            const isCurrent = i === activeIdx;
            const isDone = i < activeIdx || status === "done";
            const isErr = status === "error" && (i === activeIdx || activeIdx === -1);
            return (
              <div key={s} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className="w-2 h-2 rounded-full transition-all"
                    style={{
                      background: isErr
                        ? "var(--ra-red)"
                        : isDone || isCurrent
                        ? "var(--ra-accent)"
                        : "var(--ra-border)",
                      boxShadow: isCurrent && !isErr
                        ? "0 0 6px var(--ra-accent)"
                        : "none",
                    }}
                  />
                  <span
                    className="text-[10px] font-mono mt-1 uppercase tracking-wider"
                    style={{
                      color: isDone || isCurrent
                        ? "var(--ra-accent)"
                        : "var(--ra-muted)",
                    }}
                  >
                    {STAGE_LABELS[s]}
                  </span>
                </div>
                {i < stageList.length - 1 && (
                  <div
                    className="flex-1 h-px -mt-4 mx-1"
                    style={{
                      background: isDone ? "var(--ra-accent)" : "var(--ra-border)",
                      opacity: isDone ? 0.4 : 1,
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Terminal log */}
        <div
          className="rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--ra-border)", background: "var(--ra-surface)" }}
        >
          {/* Terminal chrome */}
          <div
            className="flex items-center gap-1.5 px-4 py-2.5 border-b"
            style={{ borderColor: "var(--ra-border)", background: "var(--ra-elevated)" }}
          >
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--ra-red)", opacity: 0.7 }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#f59e0b", opacity: 0.7 }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--ra-accent)", opacity: 0.7 }} />
            <span
              className="ml-3 text-xs font-mono"
              style={{ color: "var(--ra-muted)" }}
            >
              job/{job_id}
            </span>
          </div>

          {/* Log output */}
          <div
            className="h-72 overflow-y-auto p-4 space-y-1"
            style={{ background: "var(--ra-bg)" }}
          >
            {logs.map((line, i) => (
              <div key={i} className="log-line flex items-start gap-3 text-sm font-mono">
                <span style={{ color: "var(--ra-muted)", flexShrink: 0 }}>[{line.ts}]</span>
                <span
                  style={{
                    color: line.isError ? "var(--ra-red)" : "var(--ra-code)",
                    opacity: i < logs.length - 1 ? 0.7 : 1,
                  }}
                >
                  {line.isError ? "✕ " : status === "done" && i === logs.length - 1 ? "✓ " : "▶ "}
                  {line.text}
                </span>
              </div>
            ))}
            {status !== "done" && status !== "error" && (
              <div className="flex items-center gap-3 text-sm font-mono">
                <span style={{ color: "var(--ra-muted)" }}>
                  [{new Date().toLocaleTimeString("en-US", { hour12: false })}]
                </span>
                <span style={{ color: "var(--ra-accent)" }}>
                  <span className="animate-blink">▎</span>
                </span>
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Status summary */}
        <div
          className="rounded-xl border p-4 flex items-center gap-4"
          style={{
            borderColor: status === "error"
              ? "rgba(255,77,109,0.3)"
              : status === "done"
              ? "rgba(0,229,160,0.3)"
              : "var(--ra-border)",
            background: "var(--ra-surface)",
          }}
        >
          {status === "error" ? (
            <XCircle className="w-5 h-5 flex-shrink-0" style={{ color: "var(--ra-red)" }} />
          ) : status === "done" ? (
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" style={{ color: "var(--ra-accent)" }} />
          ) : (
            <div
              className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin flex-shrink-0"
              style={{ borderColor: `var(--ra-accent) var(--ra-accent) var(--ra-accent) transparent` }}
            />
          )}
          <div>
            <p
              className="text-sm font-semibold"
              style={{
                color: status === "error"
                  ? "var(--ra-red)"
                  : status === "done"
                  ? "var(--ra-accent)"
                  : "var(--ra-text)",
              }}
            >
              {status === "error" ? "Task Failed" : status === "done" ? "Analysis Complete" : STAGE_LABELS[stage] || stage}
            </p>
            <p className="text-xs font-mono mt-0.5" style={{ color: "var(--ra-muted)" }}>
              {errorMsg || message}
            </p>
          </div>
        </div>

        {status === "error" && (
          <button
            onClick={() => router.push("/")}
            className="text-sm font-mono underline underline-offset-4 transition-colors"
            style={{ color: "var(--ra-muted)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--ra-text)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ra-muted)")}
          >
            ← Return to Home
          </button>
        )}
      </div>
    </main>
  );
}
