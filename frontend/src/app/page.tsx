"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowRight, Loader2, Clock, ChevronRight } from "lucide-react";
import axios from "axios";

const TYPEWRITER_PHRASES = [
  "Find where auth is implemented.",
  "Map your API surface.",
  "Ask the codebase anything.",
  "Understand unfamiliar code fast.",
];

function useTypewriter(phrases: string[], speed = 60, pause = 2000) {
  const [text, setText] = useState("");
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [charIdx, setCharIdx] = useState(0);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const current = phrases[phraseIdx];
    const delay = deleting ? speed / 2 : charIdx === current.length ? pause : speed;

    const timer = setTimeout(() => {
      if (!deleting) {
        if (charIdx < current.length) {
          setText(current.slice(0, charIdx + 1));
          setCharIdx((c) => c + 1);
        } else {
          setDeleting(true);
        }
      } else {
        if (charIdx > 0) {
          setText(current.slice(0, charIdx - 1));
          setCharIdx((c) => c - 1);
        } else {
          setDeleting(false);
          setPhraseIdx((p) => (p + 1) % phrases.length);
        }
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [charIdx, deleting, phraseIdx, phrases, speed, pause]);

  return text;
}

export default function Home() {
  const [repoUrl, setRepoUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recentRepos, setRecentRepos] = useState<{ url: string; snapshotId: string; name: string }[]>([]);
  const router = useRouter();
  const typewriterText = useTypewriter(TYPEWRITER_PHRASES);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("ra_recent_repos");
      if (stored) setRecentRepos(JSON.parse(stored));
    } catch { /* ignore */ }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.includes("github.com")) {
      setError("Please enter a valid GitHub repository URL.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      const { data } = await axios.post("http://127.0.0.1:8000/api/analyze", {
        repo_url: repoUrl,
      });
      router.push(`/job/${data.job_id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to analyze repository. Is the backend running?");
      setLoading(false);
    }
  };

  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center p-6 relative overflow-hidden"
      style={{ background: "var(--ra-bg)" }}
    >
      {/* Subtle radial glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(0,229,160,0.07) 0%, transparent 70%)",
        }}
      />

      <div className="z-10 w-full max-w-2xl space-y-10 animate-fade-up">

        {/* Logotype */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 mb-4">
            <span
              className="text-xs font-mono tracking-widest uppercase px-2 py-0.5 rounded border"
              style={{
                color: "var(--ra-accent)",
                borderColor: "rgba(0,229,160,0.3)",
                background: "var(--ra-accent-dim)",
              }}
            >
              local · private · open-source
            </span>
          </div>
          <h1
            className="text-5xl md:text-6xl font-bold leading-tight tracking-tight"
            style={{ fontFamily: "var(--font-display)", color: "var(--ra-text)" }}
          >
            Understand any
            <br />
            <span style={{ color: "var(--ra-accent)" }}>GitHub repo.</span>
          </h1>
          <p
            className="text-lg mt-3 h-7"
            style={{ fontFamily: "var(--font-mono)", color: "var(--ra-muted)", fontSize: "0.95rem" }}
          >
            {typewriterText}
            <span className="animate-blink" style={{ color: "var(--ra-accent)" }}>▎</span>
          </p>
        </div>

        {/* Input form */}
        <div>
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
            <Input
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="flex-1 h-12 text-sm font-mono border-2 rounded-lg"
              style={{
                background: "transparent",
                borderColor: "var(--ra-border)",
                color: "var(--ra-text)",
                fontFamily: "var(--font-mono)",
              }}
              disabled={loading}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--ra-accent)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--ra-border)")}
            />
            <Button
              type="submit"
              className="h-12 px-7 font-semibold rounded-lg text-sm transition-all disabled:opacity-40"
              style={{
                background: loading || !repoUrl ? "var(--ra-elevated)" : "var(--ra-accent)",
                color: loading || !repoUrl ? "var(--ra-muted)" : "#0a0a0f",
                boxShadow: !loading && repoUrl ? "0 0 20px var(--ra-accent-glow)" : "none",
              }}
              disabled={loading || !repoUrl}
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  Analyze <ArrowRight className="w-4 h-4 ml-1.5" />
                </>
              )}
            </Button>
          </form>
          {error && (
            <p
              className="text-sm mt-3 font-mono"
              style={{ color: "var(--ra-red)" }}
            >
              ✕ {error}
            </p>
          )}
        </div>

        {/* Recent repos */}
        {recentRepos.length > 0 && (
          <div className="space-y-2">
            <p
              className="text-xs uppercase tracking-widest font-mono"
              style={{ color: "var(--ra-muted)" }}
            >
              <Clock className="w-3 h-3 inline mr-1.5 relative -top-px" />
              Recent
            </p>
            <ul className="space-y-1">
              {recentRepos.slice(0, 5).map((repo) => (
                <li key={repo.snapshotId}>
                  <button
                    onClick={() => router.push(`/dashboard/${repo.snapshotId}`)}
                    className="w-full text-left flex items-center justify-between px-3 py-2 rounded-lg text-sm font-mono transition-colors group"
                    style={{ color: "var(--ra-muted)" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "var(--ra-elevated)";
                      e.currentTarget.style.color = "var(--ra-text)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                      e.currentTarget.style.color = "var(--ra-muted)";
                    }}
                  >
                    <span>{repo.name}</span>
                    <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--ra-accent)" }} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Footer */}
        <p
          className="text-xs font-mono pb-2"
          style={{ color: "var(--ra-muted)", opacity: 0.5 }}
        >
          local-first · pgvector · ollama
        </p>
      </div>
    </main>
  );
}
