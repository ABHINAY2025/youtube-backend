import { useEffect, useState } from "react";
import { api, setToken } from "./api";
import Mascot from "./components/Mascot";
import AuthModal from "./components/AuthModal";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fmtDuration(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

export default function App() {
  const [me, setMe] = useState(null);
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState(null);
  const [status, setStatus] = useState(null); // {msg, error}
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState(null); // {status, progress, phase, speed, eta}
  const [authOpen, setAuthOpen] = useState(false);
  const [authReason, setAuthReason] = useState("");
  const [srv, setSrv] = useState(null); // { proxy_configured, ffmpeg }

  const refreshMe = () => api.me().then(setMe).catch(() => {});
  useEffect(() => {
    refreshMe();
    api.status().then(setSrv).catch(() => {});
  }, []);

  function logout() {
    setToken("");
    refreshMe();
  }

  async function fetchInfo(e) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setInfo(null);
    setJob(null);
    setStatus({ msg: "Reading link…", error: false });
    try {
      const data = await api.info(url.trim());
      setInfo(data);
      setStatus(null);
    } catch (err) {
      setStatus({ msg: err.message, error: true });
    } finally {
      setLoading(false);
    }
  }

  async function startDownload(q) {
    setJob({ status: "starting", progress: 0, phase: "PREPARING…" });
    try {
      const { job_id } = await api.download(url.trim(), q.format_id, q.mode);

      // Poll until ready or error.
      while (true) {
        await sleep(600);
        const p = await api.progress(job_id);
        if (p.status === "error") throw new Error(p.error || "Download failed.");
        setJob(p);
        if (p.status === "ready") break;
      }

      // Trigger the browser download of the finished file.
      const a = document.createElement("a");
      a.href = api.fileUrl(job_id);
      document.body.appendChild(a);
      a.click();
      a.remove();

      setJob({ status: "done", progress: 100, phase: "DONE! 🎉" });
      refreshMe();
      setTimeout(() => setJob(null), 3500);
    } catch (err) {
      setJob(null);
      if (err.code === "register_required") {
        setAuthReason("You've used your 2 free downloads. Register to keep going.");
        setAuthOpen(true);
      } else if (err.code === "daily_limit") {
        setStatus({ msg: err.message, error: true });
      } else {
        setStatus({ msg: err.message, error: true });
      }
    }
  }

  const quotaLabel = () => {
    if (!me) return "";
    if (me.role === "admin") return "ADMIN · UNLIMITED";
    if (me.remaining === null) return "UNLIMITED";
    if (me.authenticated) return `${me.remaining} LEFT TODAY`;
    return `${me.remaining} FREE LEFT`;
  };

  const busy = job && !["done"].includes(job.status);

  return (
    <>
      <div className="blob-field" aria-hidden="true">
        {["b1", "b2", "b3", "b4", "b5", "b6"].map((c) => (
          <span key={c} className={`blob ${c}`} />
        ))}
      </div>

      <main className="wrap">
        {/* top bar: quota + auth */}
        <div className="topbar">
          <span className="quota-badge">{quotaLabel()}</span>
          {me?.authenticated ? (
            <span className="auth-actions">
              <span className="user-name">@{me.username}</span>
              <button className="link-btn" onClick={logout}>
                LOGOUT
              </button>
            </span>
          ) : (
            <button
              className="link-btn"
              onClick={() => {
                setAuthReason("");
                setAuthOpen(true);
              }}
            >
              LOGIN
            </button>
          )}
        </div>

        {srv && srv.proxy_configured === false && (
          <div className="notice">
            ⚠️ Heads up: this server has no proxy configured, so YouTube may block
            downloads. (Admin: set <code>YTDLP_PROXY</code> to fix.)
          </div>
        )}

        <header>
          <div className="brand">
            <img className="brand-mascot" src="./mascot.jpeg" alt="devX mascot" />
            <h1 className="logo">
              <span className="l-d">d</span>
              <span className="l-e">e</span>
              <span className="l-v">v</span>
              <span className="l-x">X</span>
            </h1>
          </div>
          <p className="tagline">VIDEO&nbsp;DOWNLOADER</p>
          <p className="sub">Paste a link · pick a quality · download.</p>
        </header>

        <form onSubmit={fetchInfo} className="input-row" autoComplete="off">
          <input
            type="url"
            placeholder="https://youtu.be/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <button type="submit" disabled={loading}>
            {loading ? "…" : "FETCH"}
          </button>
        </form>

        {status && (
          <p className={`status ${status.error ? "error" : ""}`}>{status.msg}</p>
        )}

        {info && (
          <section className="card">
            <div className="meta">
              {info.thumbnail && (
                <img id="thumb" src={info.thumbnail} alt="thumbnail" />
              )}
              <div className="meta-text">
                <h2>{info.title}</h2>
                <p className="muted">{info.uploader}</p>
                {info.duration && (
                  <p className="muted">Duration: {fmtDuration(info.duration)}</p>
                )}
              </div>
            </div>

            <h3 className="section-title">CHOOSE QUALITY</h3>
            <div className="qualities">
              {info.qualities.length === 0 && (
                <p className="muted">No downloadable video formats found.</p>
              )}
              {info.qualities.map((q) => (
                <button
                  key={q.label}
                  className="q-btn"
                  disabled={busy}
                  onClick={() => startDownload(q)}
                >
                  <span className="q-label">{q.label}</span>
                  <span className="q-sub">
                    MP4{q.filesize ? ` · ${q.filesize}` : ""}
                  </span>
                </button>
              ))}
              {info.ffmpeg && (
                <button
                  className="q-btn audio"
                  disabled={busy}
                  onClick={() =>
                    startDownload({ format_id: "bestaudio/best", mode: "audio", label: "audio" })
                  }
                >
                  <span className="q-label">Audio</span>
                  <span className="q-sub">MP3 · 192kbps</span>
                </button>
              )}
            </div>

            {job && (
              <div className="progress" data-status={job.status}>
                <div className="dl-mascot">
                  <Mascot />
                  <span className="bubble bub1" />
                  <span className="bubble bub2" />
                  <span className="bubble bub3" />
                  <span className="bubble bub4" />
                </div>
                <div className="progress-head">
                  <span className="phase">
                    {(job.phase || job.status || "").toString().toUpperCase()}
                  </span>
                  <span className="muted pct">
                    {job.status === "downloading" && job.progress != null
                      ? `${job.progress}%`
                      : job.status === "ready" || job.status === "done"
                      ? "100%"
                      : ""}
                  </span>
                </div>
                <div className="bar-track">
                  <div
                    className={
                      "bar-fill" +
                      (job.status === "processing" || job.status === "starting"
                        ? " indeterminate"
                        : "") +
                      (job.status === "ready" || job.status === "done" ? " done" : "")
                    }
                    style={{
                      width:
                        job.status === "downloading" && job.progress != null
                          ? `${job.progress}%`
                          : job.status === "ready" || job.status === "done"
                          ? "100%"
                          : undefined,
                    }}
                  />
                </div>
                <div className="progress-meta muted small">
                  {job.status === "downloading"
                    ? [job.speed && `${job.speed}/s`, job.eta != null && `ETA ${job.eta}s`]
                        .filter(Boolean)
                        .join("  ·  ")
                    : job.status === "processing"
                    ? "Almost there…"
                    : job.status === "done"
                    ? "Check your downloads folder."
                    : ""}
                </div>
              </div>
            )}
          </section>
        )}

        <footer className="muted small">
          {info?.ffmpeg === false &&
            "ffmpeg not available — only formats with built-in audio are shown."}
        </footer>
        <p className="copyright small">
          made with <span className="heart">♥</span> by <strong>devXchange</strong> — for
          personal &amp; authorized use only
        </p>
      </main>

      <AuthModal
        open={authOpen}
        reason={authReason}
        onClose={() => setAuthOpen(false)}
        onAuthed={() => refreshMe()}
      />
    </>
  );
}
