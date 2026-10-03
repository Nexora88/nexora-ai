"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Repo = { full_name: string; private: boolean; default_branch: string };

export default function ExtensionsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    const t = localStorage.getItem("nexora_token");
    if (!t) {
      router.push("/");
      return;
    }
    setToken(t);
    load(t);
  }, [router]);

  const headers = (t: string) => ({ Authorization: `Bearer ${t}` });

  const load = async (t: string) => {
    setLoading(true);
    setError("");
    try {
      const st = await axios.get(`${API}/ship/status`, { headers: headers(t) });
      setStatus(st.data);
      if (st.data.connected) {
        const rp = await axios.get(`${API}/ship/repos`, { headers: headers(t) });
        setRepos(rp.data.repos || []);
        setSelected(rp.data.default_repo || "");
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const connect = async () => {
    if (!token) return;
    try {
      const res = await axios.get(`${API}/ship/connect`, { headers: headers(token) });
      window.location.href = res.data.authorize_url;
    } catch (e: any) {
      setError(e.response?.data?.detail || "OAuth başlatılamadı");
    }
  };

  const saveRepo = async () => {
    if (!token || !selected) return;
    await axios.post(
      `${API}/ship/default-repo`,
      { repo: selected },
      { headers: headers(token) }
    );
    await load(token);
  };

  const disconnect = async () => {
    if (!token) return;
    await axios.delete(`${API}/ship/disconnect`, { headers: headers(token) });
    await load(token);
  };

  return (
    <div style={s.page}>
      <header style={s.header}>
        <div style={s.brand} onClick={() => router.push("/")}>NEXORA</div>
        <div style={s.sub}>EKLENTİLER</div>
        <button style={s.ghost} onClick={() => router.push("/")}>Core</button>
      </header>

      <main style={s.main}>
        <h1 style={s.title}>Eklentiler</h1>
        <p style={s.desc}>
          Dış sistemleri bağla. Ship ile Nexora, seçtiğin repoya branch · commit · PR üretir.
          İşlem sırasında adımları canlı görürsün — sadece “yükleniyor” değil.
        </p>

        {error && <div style={s.error}>{error}</div>}
        {loading && <div style={s.muted}>Yükleniyor…</div>}

        {/* GitHub Ship kartı */}
        <section style={s.card}>
          <div style={s.cardTop}>
            <div>
              <div style={s.cardTitle}>GitHub Ship</div>
              <div style={s.cardMeta}>
                {status?.connected
                  ? `Bağlı · @${status.github_username || "user"}`
                  : "Bağlı değil"}
                {" · "}
                {status?.ship_token_cost ?? 10} token / ship
              </div>
            </div>
            {!status?.connected ? (
              <button style={s.primary} onClick={connect} disabled={!status?.oauth_ready}>
                Kur
              </button>
            ) : (
              <button style={s.ghost} onClick={disconnect}>Bağlantıyı kes</button>
            )}
          </div>

          {!status?.oauth_ready && (
            <div style={s.warn}>
              Sunucuda GITHUB_CLIENT_ID / SECRET tanımlı değil. .env’e ekle.
            </div>
          )}

          {status?.connected && (
            <div style={s.repoBlock}>
              <div style={s.label}>Varsayılan repo</div>
              <select
                style={s.select}
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Seç…</option>
                {repos.map((r) => (
                  <option key={r.full_name} value={r.full_name}>
                    {r.full_name}{r.private ? " (private)" : ""}
                  </option>
                ))}
              </select>
              <button style={s.primary} onClick={saveRepo} disabled={!selected}>
                Kaydet
              </button>
              {status.default_repo && (
                <div style={s.ok}>Aktif repo: {status.default_repo}</div>
              )}
            </div>
          )}

          <div style={s.stepsHint}>
            Ship adımları: Doğrula → Repo → Branch → Kod yaz → Commit → Push → PR
          </div>
        </section>
      </main>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#0D0D1A", color: "#e0e0e0", fontFamily: "system-ui, sans-serif" },
  header: { display: "flex", alignItems: "center", gap: 16, padding: "14px 20px", borderBottom: "1px solid #151520" },
  brand: { fontWeight: 700, letterSpacing: 3, cursor: "pointer" },
  sub: { fontSize: 11, color: "#00F0FF", letterSpacing: 2 },
  ghost: { marginLeft: "auto", padding: "8px 12px", border: "1px solid #333", background: "transparent", color: "#aaa", cursor: "pointer" },
  main: { maxWidth: 640, margin: "0 auto", padding: 24 },
  title: { fontSize: 22, letterSpacing: 2, fontWeight: 600 },
  desc: { color: "#777", fontSize: 14, lineHeight: 1.5, marginTop: 8, marginBottom: 24 },
  card: { border: "1px solid #1a1a2e", padding: 20, background: "#0a0a12" },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" },
  cardTitle: { fontSize: 16, fontWeight: 600 },
  cardMeta: { fontSize: 12, color: "#666", marginTop: 4 },
  primary: { padding: "10px 16px", border: "1px solid #00F0FF", background: "transparent", color: "#00F0FF", fontWeight: 600, cursor: "pointer" },
  repoBlock: { marginTop: 20, display: "flex", flexDirection: "column", gap: 10 },
  label: { fontSize: 11, letterSpacing: 1, color: "#666" },
  select: { padding: 12, background: "#000", color: "#eee", border: "1px solid #333" },
  ok: { fontSize: 12, color: "#00F0FF" },
  warn: { marginTop: 12, fontSize: 12, color: "#ffaa66" },
  error: { color: "#ff4466", marginBottom: 12, fontSize: 13 },
  muted: { color: "#555" },
  stepsHint: { marginTop: 16, fontSize: 11, color: "#444", letterSpacing: 0.5 },
};
